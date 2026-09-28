"""Stage-3 spec-derived HTTP checks. Optional extra URLs are actual stage-1/2 sources."""
import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from check_service import BASE, DAY, FIXTURE, USER, body, call, expect, reset


def fixture():
    data = copy.deepcopy(FIXTURE)
    data['users'].append(dict(id='other', email='other@example.test', password='another password', display_name='Other'))
    data['restaurants'][0]['manager_user_ids'] = ['user']
    data['restaurants'][0]['combinable'] = [['b', 'a']]
    return data


def policy(effective='2090-06-01', duration=60, cutoff=0, capacities=None):
    return dict(effective_from=effective, slot_minutes=30, reservation_duration_minutes=duration,
                cancellation_cutoff_minutes=cutoff,
                opening_hours=copy.deepcopy(FIXTURE['restaurants'][0]['opening_hours']),
                capacities=capacities or {'a': 4, 'b': 4})


def create(token, key, fields=None):
    return expect(*call('POST', '/reservations', fields or body(), token, key), 201)


def history(ref, token):
    return expect(*call('GET', '/reservations/' + ref + '/history', token=token), 200)['entries']


def export():
    return expect(*call('GET', '/_test/export'), 200)


def publish(token, key, **kwargs):
    return expect(*call('POST', '/restaurants/restaurant/policies', policy(**kwargs), token, key), 201)


def run():
    token = reset(fixture())
    other = expect(*call('POST', '/auth/login', fixture()['users'][1]), 200)['token']
    old = create(token, 'original')
    assert old['revision'] == 1 and old['accepted_terms']['policy_version'] == 0
    original_history = history(old['reference'], token)
    assert [c['field'] for c in original_history[0]['changes']] == ['table_id', 'starts_at_local', 'party_size']
    for suffix in ['history', 'decision']:
        expect(*call('GET', '/reservations/' + old['reference'] + '/' + suffix), 404, 'not_found')
        expect(*call('GET', '/reservations/' + old['reference'] + '/' + suffix, token=other), 404, 'not_found')
    expect(*call('POST', '/restaurants/restaurant/policies', policy(), other, 'denied'), 403, 'forbidden')
    expect(*call('POST', '/restaurants/restaurant/policies', policy(), key='no-token'), 401, 'unauthenticated')
    p1 = publish(token, 'later', effective='2090-06-10', duration=120)
    p2 = publish(token, 'earlier', effective='2090-06-01', duration=30)
    assert p1['policy_version'] == 1 and p2['policy_version'] == 2
    assert expect(*call('GET', '/reservations/' + old['reference'], token=token), 200) == old
    assert history(old['reference'], token) == original_history
    assert expect(*call('PATCH', '/reservations/' + old['reference'], {'party_size': 2}, token), 200) == old
    updated = expect(*call('PATCH', '/reservations/' + old['reference'], {'party_size': 3, 'expected_revision': 1}, token), 200)
    assert updated['revision'] == 2 and updated['accepted_terms']['policy_version'] == 2
    assert updated['ends_at'].startswith(DAY + 'T18:30:00')
    request = body('b'); request['starts_at_local'] = '2090-06-12T18:00'
    later = create(token, 'future', request)
    assert later['accepted_terms']['policy_version'] == 1
    p3 = publish(token, 'tie', effective='2090-06-10', duration=60)
    request['starts_at_local'] = '2090-06-12T20:00'
    assert create(token, 'tie-booking', request)['accepted_terms']['policy_version'] == p3['policy_version'] == 3
    assert expect(*call('GET', '/restaurants/restaurant'), 200)['reservation_duration_minutes'] == 90
    assert [p['policy_version'] for p in expect(*call('GET', '/restaurants/restaurant/policies'), 200)['policies']] == [1, 2, 3]
    assert expect(*call('POST', '/reservations', body(), token, 'original'), 200) == old
    print('PASS manager privacy, immutable dated policies, out-of-order dates/ties, accepted terms, resulting-policy amendment and no-op invariance')

    before = export()
    invalids = [dict(policy(), slot_minutes=True), dict(policy(), reservation_duration_minutes=1441),
                dict(policy(), cancellation_cutoff_minutes=-1), dict(policy(), capacities={'a': 2}),
                dict(policy(), capacities={'a': 101, 'b': 4}), dict(policy(), effective_from='2090-02-30'),
                dict(policy(), opening_hours=[{'weekday': 'mon', 'opens': '18:00', 'closes': '23:00'}] * 2), {}]
    for invalid in invalids:
        expect(*call('POST', '/restaurants/restaurant/policies', invalid, token, 'invalid'), 422, 'validation_failed')
        assert export() == before
    expect(*call('POST', '/restaurants/restaurant/policies', {}, token, 'later'), 409, 'idempotency_key_reuse')
    # Both availability rules must be evaluated, not short-circuited by capacity.
    query = '/availability?restaurant_id=restaurant&date=' + DAY + '&party_size=5'
    assert all('explain' not in s for s in expect(*call('GET', query), 200)['slots'])
    slot = next(s for s in expect(*call('GET', query + '&explain=true'), 200)['slots'] if s['starts_at_local'].endswith('18:00'))
    assert [x['table_id'] for x in slot['explain']] == ['a', 'b']
    assert slot['explain'][0]['rules'] == [{'rule': 'capacity', 'holds': False}, {'rule': 'no_overlap', 'holds': False}]
    assert slot['explain'][1]['rules'] == [{'rule': 'capacity', 'holds': False}, {'rule': 'no_overlap', 'holds': True}]
    assert all(x['policy_version'] == 2 for x in slot['explain'])
    for value in ['false', '1', '']:
        expect(*call('GET', query + '&explain=' + value), 422, 'validation_failed')
    print('PASS policy validation rollback, original policy receipts, independent ordered explanations and strict explain parameter')

    token = reset(fixture())
    item = create(token, 'race')
    path = '/reservations/' + item['reference']
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda _: call('PATCH', path, {'party_size': 3, 'expected_revision': 1}, token), range(50)))
    assert sum(s == 200 for s, _ in replies) == 1 and sum(s == 409 for s, _ in replies) == 49
    assert all(r['error']['code'] == 'stale_revision' for s, r in replies if s == 409)
    expect(*call('PATCH', path, {'party_size': False, 'expected_revision': 1}, token), 409, 'stale_revision')
    expect(*call('PATCH', path, {'expected_revision': True}, token), 422, 'validation_failed')
    history_before = history(item['reference'], token)
    expect(*call('PATCH', path, {'party_size': 3}, token), 200)
    assert history(item['reference'], token) == history_before
    cancelled = expect(*call('POST', path + '/cancel', {}, token), 200)
    assert cancelled['revision'] == 3
    assert expect(*call('POST', path + '/cancel', {}, token), 200) == cancelled
    entries = history(item['reference'], token)
    assert [h['seq'] for h in entries] == [1, 2, 3] and entries[-1]['changes'] == []
    assert expect(*call('GET', path + '/decision', token=token), 200)['revision'] == 3
    print('PASS 50-way expected-revision race, stale-before-field validation, no-op history, single cancellation increment and private decision')

    series_checks()
    cutoff_checks()
    dst_checks()
    for source in sys.argv[2:]:
        migration(source)
    print('All supplemental stage-3 checks passed')


def series_checks():
    token = reset(fixture())
    fields = body(); fields.pop('table_id'); fields.update(table_ids=['a', 'b'], party_size=6)
    anchor = create(token, 'anchor', fields)
    ref = anchor['reference']
    h0 = history(ref, token)
    assert h0[0]['changes'][0] == {'field': 'table_ids', 'from': None, 'to': ['b', 'a']}
    request = {'anchor_reference': ref, 'count': 3, 'interval_weeks': 1}
    before = export()
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda _: call('POST', '/series', request, token, 'series'), range(50)))
    assert sum(s == 201 for s, _ in replies) == 1 and sum(s == 200 for s, _ in replies) == 49
    series = replies[0][1]
    assert all(value == series for _, value in replies)
    assert series['revision'] == 1 and series['occurrences'][0]['reservation'] == anchor
    assert history(ref, token) == h0
    assert export()['state']['restaurant_revisions']['restaurant'] == before['state']['restaurant_revisions']['restaurant'] + 1
    sid = series['series_id']; path = '/series/' + sid
    expect(*call('GET', path), 404, 'not_found')
    expect(*call('POST', '/series', request, token, 'adopted'), 409, 'already_in_series')
    refs = [o['reference'] for o in series['occurrences']]
    expect(*call('PATCH', '/reservations/' + refs[1], {'table_ids': ['a', 'b']}, token), 200)
    assert expect(*call('GET', path, token=token), 200) == series
    changed = expect(*call('PATCH', '/reservations/' + refs[1], {'party_size': 5}, token), 200)
    current = expect(*call('GET', path, token=token), 200)
    assert current['revision'] == 2 and current['occurrences'][1]['exception']
    expect(*call('PATCH', '/reservations/' + refs[1], {'party_size': 6}, token), 200)
    current = expect(*call('GET', path, token=token), 200)
    assert current['revision'] == 3 and current['occurrences'][1]['exception']
    state_before = export()
    moves = {'moves': [{'reference': refs[0], 'party_size': 4}, {'reference': refs[2], 'party_size': 4}]}
    moved = expect(*call('POST', '/reservation-moves', moves, token, 'move'), 201)
    current = expect(*call('GET', path, token=token), 200)
    assert current['revision'] == 4 and all(o['exception'] for o in current['occurrences'])
    assert export()['state']['restaurant_revisions']['restaurant'] == state_before['state']['restaurant_revisions']['restaurant'] + 1
    expect(*call('POST', '/reservations/' + ref + '/cancel', {}, token), 200)
    current = expect(*call('GET', path, token=token), 200)
    assert current['revision'] == 5 and current['occurrences'][0]['reservation']['status'] == 'cancelled'
    assert all(o['reservation']['status'] == 'confirmed' for o in current['occurrences'][1:])
    assert expect(*call('POST', '/series', request, token, 'series'), 200) == series
    assert expect(*call('POST', '/reservation-moves', moves, token, 'move'), 200) == moved
    snapshot = export()
    expect(*call('POST', '/_test/import', snapshot), 204)
    assert export() == snapshot
    assert expect(*call('POST', '/series', request, token, 'series'), 200) == series
    bad = copy.deepcopy(snapshot); bad['state']['histories'][ref][-1]['seq'] = 99
    expect(*call('POST', '/_test/import', bad), 422)
    assert export() == snapshot
    print('PASS pair history, 50-way adoption, unchanged anchor, permanent exceptions, once-per-series/batch counters, independent cancellation and original series/move snapshots')

    # First failing occurrence wins and no tentative occurrence/counter/receipt leaks.
    token = reset(fixture())
    anchor = create(token, 'anchor')
    blocked = body(); blocked['starts_at_local'] = (date.fromisoformat(DAY) + timedelta(days=7)).isoformat() + 'T18:00'
    blocker = create(token, 'blocker', blocked)
    publish(token, 'later-bad', effective=(date.fromisoformat(DAY) + timedelta(days=14)).isoformat(), capacities={'a': 1, 'b': 4})
    request = {'anchor_reference': anchor['reference'], 'count': 3, 'interval_weeks': 1}
    before = export()
    expect(*call('POST', '/series', request, token, 'failed'), 409, 'table_unavailable')
    assert export() == before
    expect(*call('POST', '/reservations/' + blocker['reference'] + '/cancel', {}, token), 200)
    before = export()
    expect(*call('POST', '/series', request, token, 'failed'), 422, 'party_exceeds_capacity')
    assert export() == before
    publish(token, 'repair', effective=(date.fromisoformat(DAY) + timedelta(days=14)).isoformat())
    adopted = expect(*call('POST', '/series', request, token, 'failed'), 201)
    assert [o['reservation']['accepted_terms']['policy_version'] for o in adopted['occurrences']] == [0, 0, 2]
    print('PASS occurrence-index error precedence, policy-per-date adoption, atomic rollback and failed-key reuse')


def cutoff_checks():
    data = fixture(); data['restaurants'][0]['cancellation_cutoff_minutes'] = 10080
    token = reset(data)
    future = datetime.now(timezone.utc) + timedelta(days=2)
    request = body(); request['starts_at_local'] = future.date().isoformat() + 'T18:00'
    record = create(token, 'locked', request)
    publish(token, 'looser', effective=future.date().isoformat(), cutoff=0)
    expect(*call('PATCH', '/reservations/' + record['reference'], {'party_size': 3}, token), 409, 'cutoff_passed')
    expect(*call('POST', '/reservations/' + record['reference'] + '/cancel', {}, token), 409, 'cutoff_passed')
    expect(*call('PATCH', '/reservations/' + record['reference'], {'expected_revision': 999}, token), 409, 'stale_revision')
    print('PASS accepted cutoff survives looser policy; stale revision precedes cutoff')


def dst_checks():
    for zone in ['America/New_York', 'Europe/Berlin']:
        if zone == 'America/New_York':
            spring = date(2090, 3, 8); spring += timedelta(days=(6 - spring.weekday()) % 7)
            fall = date(2090, 11, 1); fall += timedelta(days=(6 - fall.weekday()) % 7)
            clock, offset = '01:30', '-04:00'
        else:
            spring = date(2090, 3, 31); spring -= timedelta(days=(spring.weekday() - 6) % 7)
            fall = date(2090, 10, 31); fall -= timedelta(days=(fall.weekday() - 6) % 7)
            clock, offset = '02:30', '+02:00'
        data = fixture(); data['restaurants'][0]['timezone'] = zone
        token = reset(data)
        request = body(); request['starts_at_local'] = (spring - timedelta(days=7)).isoformat() + 'T02:30'
        anchor = create(token, 'spring-anchor', request)
        before = export()
        expect(*call('POST', '/series', {'anchor_reference': anchor['reference'], 'count': 2, 'interval_weeks': 1}, token, 'gap'), 422, 'invalid_local_time')
        assert export() == before
        request['starts_at_local'] = (fall - timedelta(days=7)).isoformat() + 'T' + clock
        anchor = create(token, 'fall-anchor', request)
        adopted = expect(*call('POST', '/series', {'anchor_reference': anchor['reference'], 'count': 2, 'interval_weeks': 1}, token, 'fold'), 201)
        record = adopted['occurrences'][1]['reservation']
        assert record['starts_at'].endswith(offset)
        assert (datetime.fromisoformat(record['ends_at']) - datetime.fromisoformat(record['starts_at'])).total_seconds() == 5400
    print('PASS recurring local dates across both zones: DST gap rollback and first-fold absolute duration')


def migration(source):
    expect(*call('POST', '/_test/reset', FIXTURE, base=source), 204)
    token = expect(*call('POST', '/auth/login', USER, base=source), 200)['token']
    request = dict(body(), expected_revision=False, accepted_terms={'ignored': True})
    original = expect(*call('POST', '/reservations', request, token, 'old', base=source), 201)
    assert 'revision' not in original
    moves = {'moves': [{'reference': original['reference'], 'table_id': 'b', 'expected_revision': False}]}
    old_move = expect(*call('POST', '/reservation-moves', moves, token, 'move', base=source), 201)
    snapshot = expect(*call('GET', '/_test/export', base=source), 200)
    for _ in range(2):
        expect(*call('POST', '/_test/import', snapshot), 204)
        assert expect(*call('POST', '/reservations', request, token, 'old'), 200) == original
        assert expect(*call('POST', '/reservation-moves', moves, token, 'move'), 200) == old_move
        current = expect(*call('GET', '/reservations/' + original['reference'], token=token), 200)
        assert current['revision'] == 1 and current['accepted_terms']['policy_version'] == 0 and current['table_id'] == 'b'
        adopted = expect(*call('POST', '/series', {'anchor_reference': original['reference'], 'count': 2, 'interval_weeks': 1}, token, 'adopt'), 201)
        assert adopted['occurrences'][0]['reservation'] == current
        upgraded = export()
        expect(*call('POST', '/_test/import', upgraded), 204)
        assert expect(*call('POST', '/reservations', request, token, 'old'), 200) == original
        expect(*call('POST', '/auth/login', USER), 200)
    print('PASS real earlier-stage migration/adoption with retained identity, hashes, tokens and original create/move receipts from ' + source)


if __name__ == '__main__':
    run()
