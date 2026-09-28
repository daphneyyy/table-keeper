"""Specification-derived HTTP checks; standard library only, no product imports."""
import copy
import json
import sys
import time
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080'
DEST = sys.argv[2] if len(sys.argv) > 2 else BASE
DAY = '2090-06-05'
USER = {'id': 'user', 'email': 'user@example.test', 'password': 'sample password', 'display_name': 'Diner'}
FIXTURE = {'users': [USER], 'restaurants': [{
    'id': 'restaurant', 'name': 'Dining room', 'timezone': 'UTC', 'slot_minutes': 30,
    'reservation_duration_minutes': 90, 'cancellation_cutoff_minutes': 60,
    'opening_hours': [{'weekday': w, 'opens': '00:00', 'closes': '23:59'}
                      for w in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']],
    'tables': [{'id': 'a', 'label': 'Window', 'capacity': 4}, {'id': 'b', 'label': 'Garden', 'capacity': 4}]
}], 'reservations': []}


def call(method, path, body=None, token=None, key=None, base=BASE):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key is not None:
        headers['Idempotency-Key'] = key
    request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as exc:
        response = exc
    raw = response.read()
    return response.status, json.loads(raw) if raw else None


def expect(status, response, wanted, code=None):
    assert status == wanted, (status, response, wanted)
    if code:
        assert response['error']['code'] == code, response
    return response


def reset(fixture=FIXTURE):
    expect(*call('POST', '/_test/reset', fixture), 204)
    return expect(*call('POST', '/auth/login', USER), 200)['token']


def body(table='a', at='18:00', **extra):
    return dict(restaurant_id='restaurant', table_id=table, starts_at_local=DAY + 'T' + at, party_size=2, **extra)


def create(token, key, data):
    return expect(*call('POST', '/reservations', data, token, key), 201)


def run():
    token = reset()
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda _: call('POST', '/reservations', body(), token, 'same'), range(50)))
    assert [s for s, _ in replies].count(201) == 1
    assert [s for s, _ in replies].count(200) == 49
    assert all(r == replies[0][1] for _, r in replies)
    print('PASS 50 identical requests: one commit, immutable identical responses; %.3fs' % (time.monotonic() - start))

    token = reset()
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda i: call('POST', '/reservations', body(), token, str(i)), range(50)))
    assert [s for s, _ in replies].count(201) == 1
    assert [s for s, _ in replies].count(409) == 49
    adjacent = create(token, 'adjacent', body(at='19:30'))
    expect(*call('POST', '/reservations', body(at='19:00'), token, 'overlap'), 409, 'table_unavailable')
    print('PASS 50 conflicting requests; half-open adjacency and partial overlap')

    token = reset()
    a = create(token, 'a', body())
    b = create(token, 'b', body('b'))
    moves = {'moves': [{'reference': a['reference'], 'table_id': 'b'}, {'reference': b['reference'], 'table_id': 'a'}]}
    moved = expect(*call('POST', '/reservation-moves', moves, token, 'swap'), 201)
    assert [r['table_id'] for r in moved['reservations']] == ['b', 'a']
    before = call('GET', '/_test/export')[1]
    fail = {'moves': [{'reference': a['reference'], 'table_id': 'a'}, {'reference': b['reference'], 'table_id': 'a'}]}
    expect(*call('POST', '/reservation-moves', fail, token, 'failed'), 409, 'table_unavailable')
    assert call('GET', '/_test/export')[1] == before
    expect(*call('POST', '/reservation-moves', moves, token, 'failed'), 201)
    expect(*call('POST', '/reservation-moves', {'moves': []}, token, 'swap'), 409, 'idempotency_key_reuse')
    expect(*call('POST', '/reservations/' + a['reference'] + '/cancel', {}, token), 200)
    assert expect(*call('POST', '/reservation-moves', moves, token, 'swap'), 200) == moved
    assert expect(*call('POST', '/reservations', body(), token, 'a'), 200) == a
    print('PASS atomic swaps, failed rollback/key reuse, saved responses after cancellation')

    # JSON equality includes ignored properties; booleans never equal numbers.
    token = reset()
    original = body(ignored={'a': True, 'b': [2, 3]})
    created = create(token, 'json', original)
    alternate = body(ignored={'b': [2.0, 3], 'a': True})
    assert expect(*call('POST', '/reservations', alternate, token, 'json'), 200) == created
    alternate['ignored']['a'] = 1
    expect(*call('POST', '/reservations', alternate, token, 'json'), 409, 'idempotency_key_reuse')
    for bad in [True, '2', 0, -1, 2.5]:
        changed = body('b'); changed['party_size'] = bad
        expect(*call('POST', '/reservations', changed, token, 'invalid'), 422, 'validation_failed')
    changed = body('b'); changed['table_id'] = 2
    expect(*call('POST', '/reservations', changed, token, 'invalid'), 400, 'malformed_request')
    print('PASS JSON equality, field type distinctions, failed requests leave retry keys reusable')

    token = reset()
    raw = json.dumps(body())[:-1] + ', "ignored": 1e400}'
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token, 'Idempotency-Key': 'large'}
    req = Request(BASE + '/reservations', data=raw.encode(), headers=headers, method='POST')
    with urlopen(req, timeout=5) as result:
        assert result.status == 201
    with urlopen(BASE + '/_test/export', timeout=5) as result:
        snapshot_bytes = result.read()
        parsed = json.loads(snapshot_bytes, parse_float=Decimal)
        assert parsed['state']['receipts'][0]['body']['ignored'] == Decimal('1e400')
    req = Request(BASE + '/_test/import', data=snapshot_bytes, headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=5) as result:
        assert result.status == 204
    req = Request(BASE + '/reservations', data=raw.replace('1e400', '2e400').encode(), headers=headers, method='POST')
    try:
        urlopen(req, timeout=5)
        raise AssertionError('Distinct large JSON numbers replayed')
    except HTTPError as exc:
        assert exc.code == 409 and json.load(exc)['error']['code'] == 'idempotency_key_reuse'
    expect(*call('TRACE', '/health'), 405, 'method_not_allowed')
    print('PASS exact large-number receipts/export/import and framework error envelope')

    token = reset()
    bookings = [create(token, str(i), body(at=f'{i * 2:02d}:00')) for i in range(8)]
    noops = {'moves': [{'reference': r['reference'], 'ignored': True} for r in bookings]}
    assert expect(*call('POST', '/reservation-moves', noops, token, 'eight'), 201)['reservations'] == bookings
    expect(*call('POST', '/reservation-moves', {'moves': noops['moves'] + [noops['moves'][0]]}, token, 'nine'), 422)
    expect(*call('POST', '/reservation-moves', {'moves': [noops['moves'][0], noops['moves'][0]]}, token, 'duplicate'), 422)
    racing = {'moves': [{'reference': r['reference'], 'table_id': 'b'} for r in bookings]}
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda _: call('POST', '/reservation-moves', racing, token, 'race-moves'), range(50)))
    assert [s for s, _ in replies].count(201) == 1 and [s for s, _ in replies].count(200) == 49
    assert all(r == replies[0][1] for _, r in replies)
    expect(*call('POST', '/reservations/' + bookings[0]['reference'] + '/cancel', {}, token), 200)
    precedence = {'moves': [{'reference': bookings[0]['reference'], 'party_size': -1},
                            {'reference': 'ABSENT', 'table_id': 'missing'}]}
    expect(*call('POST', '/reservation-moves', precedence, token, 'precedence'), 409, 'reservation_cancelled')
    precedence['moves'].reverse()
    expect(*call('POST', '/reservation-moves', precedence, token, 'precedence'), 404, 'not_found')
    print('PASS 8-item no-ops, shape limits, 50-way batch replay, input-order non-occupancy errors')

    token = reset()
    past = body(); past['starts_at_local'] = '2000-01-01T18:00'
    record = create(token, 'past', past)
    expect(*call('PATCH', '/reservations/' + record['reference'], {'party_size': -1}, token), 409, 'cutoff_passed')
    expect(*call('POST', '/reservations/' + record['reference'] + '/cancel', {}, token), 409, 'cutoff_passed')
    tiny_year = expect(*call('GET', '/availability?restaurant_id=restaurant&party_size=2&date=0001-01-01'), 200)
    assert tiny_year['slots'][0]['starts_at_local'] == '0001-01-01T00:00'
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=50) as pool:
        replies = list(pool.map(lambda _: call('POST', '/auth/login', USER), range(50)))
    assert all(s == 200 for s, _ in replies) and len({r['token'] for _, r in replies}) == 50
    assert time.monotonic() - started < 5
    print('PASS past bookings, current cutoff precedence, four-digit years, 50 concurrent logins')

    for zone, spring, fall, fold_time, offset, end in [
        ('Europe/Berlin', '2026-03-29', '2026-10-25', '02:30', '+02:00', '03:00:00+01:00'),
        ('America/New_York', '2026-03-08', '2026-11-01', '01:30', '-04:00', '02:00:00-05:00')]:
        fixture = copy.deepcopy(FIXTURE)
        fixture['restaurants'][0]['timezone'] = zone
        token = reset(fixture)
        gap = body(); gap['starts_at_local'] = spring + 'T02:30'
        expect(*call('POST', '/reservations', gap, token, 'gap'), 422, 'invalid_local_time')
        available = expect(*call('GET', '/availability?restaurant_id=restaurant&party_size=2&date=' + spring), 200)
        assert not any(x['starts_at_local'][11:13] == '02' for x in available['slots'])
        folded = body(); folded['starts_at_local'] = fall + 'T' + fold_time
        record = create(token, 'fold', folded)
        assert record['starts_at'].endswith(offset) and record['ends_at'].endswith(end), record
        assert (datetime.fromisoformat(record['ends_at']) - datetime.fromisoformat(record['starts_at'])).total_seconds() == 5400
    print('PASS Berlin/New York gap omission, gap refusal, first fold and absolute duration')

    token = reset()
    original = create(token, 'original', body())
    changed = expect(*call('PATCH', '/reservations/' + original['reference'], {'party_size': 3}, token), 200)
    snapshot = expect(*call('GET', '/_test/export'), 200)
    assert 'password' not in snapshot['state']['users']['user']
    assert snapshot['state']['users']['user']['password_hash']['algorithm'] == 'scrypt'
    # Destination replacement, old-token invalidation, and repeated restore.
    expect(*call('POST', '/_test/reset', FIXTURE, base=DEST), 204)
    old_token = expect(*call('POST', '/auth/login', USER, base=DEST), 200)['token']
    for _ in range(2):
        expect(*call('POST', '/_test/import', snapshot, base=DEST), 204)
        expect(*call('GET', '/reservations', token=old_token, base=DEST), 401, 'unauthenticated')
        assert expect(*call('GET', '/reservations/' + original['reference'], token=token, base=DEST), 200) == changed
        assert expect(*call('POST', '/reservations', body(), token, 'original', base=DEST), 200) == original
        expect(*call('POST', '/auth/login', USER, base=DEST), 200)
    for damage in ['sessions', 'reservations', 'receipts', 'password_hash']:
        invalid = copy.deepcopy(snapshot)
        if damage == 'sessions':
            invalid['state']['sessions']['bad'] = 'missing'
        elif damage == 'reservations':
            invalid['state']['reservations'][original['reference']]['ends_at'] = 'nonsense'
        elif damage == 'receipts':
            invalid['state']['receipts'][0]['response']['reference'] = 'ABSENT'
        else:
            invalid['state']['users']['user']['password_hash']['n'] = 2 ** 50
        before = call('GET', '/_test/export', base=DEST)[1]
        expect(*call('POST', '/_test/import', invalid, base=DEST), 422, 'validation_failed')
        assert call('GET', '/_test/export', base=DEST)[1] == before
    print('PASS replacement/repeated import, sessions/hashes/identities/receipts, invalid-import atomic rollback')
    print('All supplemental stage-1 checks passed')


if __name__ == '__main__':
    run()
