"""Stage-2 HTTP invariants and real stage-1 migration; standard library only.

Usage: python tests/check_combinations.py STAGE2_URL [STAGE1_URL]
The optional source must be a running actual stage-1 image, not a synthetic export.
"""
import copy
import sys
from concurrent.futures import ThreadPoolExecutor

from check_service import BASE, DAY, FIXTURE, USER, body, call, expect, reset


def pair(ids, at='18:00', size=6):
    result = body(at=at)
    del result['table_id']
    result.update(table_ids=ids, party_size=size)
    return result


def run():
    fixture = copy.deepcopy(FIXTURE)
    restaurant = fixture['restaurants'][0]
    restaurant['tables'].extend([{'id': 'c', 'label': 'Terrace', 'capacity': 2},
                                 {'id': 'd', 'label': 'Courtyard', 'capacity': 2}])
    restaurant['combinable'] = [['b', 'a'], ['c', 'd'], ['b', 'c']]
    token = reset(fixture)
    query = '/availability?restaurant_id=restaurant&date=' + DAY + '&party_size=2'
    slot = expect(*call('GET', query), 200)['slots'][0]
    assert slot['available_table_ids'] == ['a', 'b', 'c', 'd']
    assert [x['table_ids'] for x in slot['available_options']] == [['a'], ['b'], ['c'], ['d'], ['b', 'a'], ['c', 'd'], ['b', 'c']]
    created = expect(*call('POST', '/reservations', pair(['a', 'b']), token, 'pair'), 201)
    assert created['table_ids'] == ['b', 'a'] and 'table_id' not in created
    for tid in ['a', 'b']:
        expect(*call('POST', '/reservations', body(tid), token, 'single-' + tid), 409, 'table_unavailable')
    expect(*call('POST', '/reservations', pair(['b', 'c']), token, 'overlap'), 409, 'table_unavailable')
    expect(*call('POST', '/reservations', pair(['a', 'c']), token, 'undeclared'), 422, 'combination_not_allowed')
    expect(*call('POST', '/reservations', pair(['a', 'a']), token, 'duplicate'), 422, 'validation_failed')
    expect(*call('POST', '/reservations', pair(['a', 'b', 'c']), token, 'three'), 422, 'combination_not_allowed')
    expect(*call('POST', '/reservations', dict(pair(['a', 'b']), table_id='a'), token, 'both'), 422, 'validation_failed')
    expect(*call('POST', '/reservations', pair(['a', 'b'], size=9), token, 'capacity'), 422, 'party_exceeds_capacity')
    before = call('GET', '/_test/export')[1]
    expect(*call('PATCH', '/reservations/' + created['reference'], {'table_id': 'a'}, token), 422, 'party_exceeds_capacity')
    assert call('GET', '/_test/export')[1] == before
    changed = expect(*call('PATCH', '/reservations/' + created['reference'], {'table_id': 'a', 'party_size': 2}, token), 200)
    assert changed['table_ids'] == ['a'] and changed['table_id'] == 'a'
    changed = expect(*call('PATCH', '/reservations/' + created['reference'], {'table_ids': ['a', 'b'], 'party_size': 6}, token), 200)
    assert changed['table_ids'] == ['b', 'a'] and 'table_id' not in changed
    assert expect(*call('PATCH', '/reservations/' + created['reference'], {'table_ids': ['b', 'a']}, token), 200) == changed
    expect(*call('POST', '/reservations/' + created['reference'] + '/cancel', {}, token), 200)
    expect(*call('POST', '/reservations', body('a'), token, 'single-a'), 201)
    expect(*call('POST', '/reservations', body('b'), token, 'single-b'), 201)
    assert expect(*call('POST', '/reservations', pair(['a', 'b']), token, 'pair'), 200) == created
    print('PASS pair declaration/order/capacity, both-member occupancy, singles/pairs amendment and cancellation, immutable receipts')

    token = reset(fixture)
    left = expect(*call('POST', '/reservations', body('a'), token, 'left'), 201)
    right = expect(*call('POST', '/reservations', body('c'), token, 'right'), 201)
    moves = {'moves': [{'reference': left['reference'], 'table_ids': ['c', 'd']},
                       {'reference': right['reference'], 'table_ids': ['a', 'b']}]}
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda _: call('POST', '/reservation-moves', moves, token, 'batch'), range(50)))
    assert sum(s == 201 for s, _ in results) == 1 and sum(s == 200 for s, _ in results) == 49
    assert all(r == results[0][1] for _, r in results)
    invalid = {'moves': [{'reference': left['reference'], 'table_ids': ['b', 'c']},
                         {'reference': right['reference'], 'table_id': 'b'}]}
    before = call('GET', '/_test/export')[1]
    expect(*call('POST', '/reservation-moves', invalid, token, 'failed'), 409, 'table_unavailable')
    assert call('GET', '/_test/export')[1] == before
    expect(*call('POST', '/_test/import', before), 204)
    assert expect(*call('POST', '/reservation-moves', moves, token, 'batch'), 200) == results[0][1]
    token = reset(fixture)
    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(lambda i: call('POST', '/reservations', pair(['a', 'b']) if i % 2 else body('a'), token, str(i)), range(50)))
    assert sum(s == 201 for s, _ in results) == 1 and sum(s == 409 for s, _ in results) == 49
    print('PASS pair atomic moves, 50 identical batch retries, rollback, export/import, 50 competing pair/single creates')

    seeded = copy.deepcopy(fixture)
    seeded['reservations'] = [dict(pair(['a', 'b']), id='seed', reference='SEED01', user_id='user', status='cancelled')]
    token = reset(seeded)
    saved = expect(*call('GET', '/reservations/SEED01', token=token), 200)
    assert saved['status'] == 'cancelled' and saved['table_ids'] == ['b', 'a']
    expect(*call('POST', '/reservations', body(), token, 'seed-free'), 201)
    print('PASS cancelled pair seed retains identity and consumes no occupancy')

    if len(sys.argv) > 2:
        migration(sys.argv[2])


def migration(source):
    expect(*call('POST', '/_test/reset', FIXTURE, base=source), 204)
    token = expect(*call('POST', '/auth/login', USER, base=source), 200)['token']
    token2 = expect(*call('POST', '/auth/login', USER, base=source), 200)['token']
    # Stage 1 ignored this future field. Migration must retain that old meaning.
    old_body = dict(body(), table_ids={'unknown_to_stage_1': True})
    original = expect(*call('POST', '/reservations', old_body, token, 'old', base=source), 201)
    assert 'table_ids' not in original, 'Source is not an actual stage-1 API'
    moves = {'moves': [{'reference': original['reference'], 'table_id': 'b', 'table_ids': False}]}
    old_moves = expect(*call('POST', '/reservation-moves', moves, token, 'move', base=source), 201)
    expect(*call('POST', '/reservations/' + original['reference'] + '/cancel', {}, token, base=source), 200)
    snapshot = expect(*call('GET', '/_test/export', base=source), 200)
    destination_token = reset()
    for _ in range(2):
        expect(*call('POST', '/_test/import', snapshot), 204)
        expect(*call('GET', '/reservations', token=destination_token), 401)
        for active in [token, token2]:
            current = expect(*call('GET', '/reservations/' + original['reference'], token=active), 200)
            assert current['table_ids'] == ['b'] and current['status'] == 'cancelled'
            assert current['reservation_id'] == original['reservation_id']
        assert expect(*call('POST', '/reservations', old_body, token, 'old'), 200) == original
        assert expect(*call('POST', '/reservation-moves', moves, token, 'move'), 200) == old_moves
        expect(*call('POST', '/auth/login', USER), 200)
        upgraded = expect(*call('GET', '/_test/export'), 200)
        expect(*call('POST', '/_test/import', upgraded), 204)
        assert expect(*call('POST', '/reservations', old_body, token, 'old'), 200) == original
    print('PASS actual stage-1→2 migration, sessions/hashes/identities/cancelled records, exact old receipts with formerly unknown table_ids, repeated stage-2 export/import')


if __name__ == '__main__':
    run()
