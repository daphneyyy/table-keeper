"""Regression for RFC3339 historic offsets and unbounded JSON number exponents."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from check_service import BASE, DEST, FIXTURE, body, call, expect, reset


def raw_call(method, path, data=None, token=None, key=None, base=BASE):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if key:
        headers['Idempotency-Key'] = key
    request = Request(base + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as exc:
        response = exc
    return response.status, response.read()


def numeric_body(number):
    return (json.dumps(body())[:-1] + ',"ignored":{"nested":[' + number + ']}}').encode()


def run():
    fixture = copy.deepcopy(FIXTURE)
    fixture['restaurants'][0]['timezone'] = 'Europe/Berlin'
    fixture['restaurants'][0]['opening_hours'] = [
        {'weekday': 'mon', 'opens': '18:00', 'closes': '23:00'}]
    token = reset(fixture)
    available = expect(*call('GET', '/availability?restaurant_id=restaurant&date=0001-01-01&party_size=2'), 200)
    first = available['slots'][0]
    assert first['starts_at_local'] == '0001-01-01T18:00'
    expected = datetime(1, 1, 1, 18, tzinfo=timezone(timedelta(seconds=3208))).astimezone(timezone.utc)
    assert datetime.fromisoformat(first['starts_at']) == expected
    request = body(); request['starts_at_local'] = first['starts_at_local']
    reservation = expect(*call('POST', '/reservations', request, token, 'historic'), 201)
    pattern = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})'
    for key in ('starts_at', 'ends_at', 'created_at'):
        assert re.fullmatch(pattern, reservation[key]), reservation[key]
    assert datetime.fromisoformat(reservation['starts_at']) == expected
    assert datetime.fromisoformat(reservation['ends_at']) == expected + timedelta(minutes=90)
    print('PASS historical Berlin instants preserved with RFC3339 timestamps')

    cases = [
        ('1e99999999999999999999', '10e99999999999999999998', '2e99999999999999999999'),
        ('-1e-99999999999999999999', '-0.1e-99999999999999999998', '1e-99999999999999999999'),
        ('-0e99999999999999999999', '0', '1'),
        # Larger-than-host conversion limits in exponent and coefficient too.
        ('1e' + '9' * 5000, '1.0e+' + '9' * 5000, '2e' + '9' * 5000),
        ('7' * 5000, '7' * 5000 + '.0', '8' * 5000),
    ]
    for original, equivalent, different in cases:
        token = reset()
        status, created = raw_call('POST', '/reservations', numeric_body(original), token, 'number')
        assert status == 201, (status, created[:200])
        status, replay = raw_call('POST', '/reservations', numeric_body(equivalent), token, 'number')
        assert status == 200 and json.loads(replay) == json.loads(created)
        status, _ = raw_call('POST', '/reservations', numeric_body(different), token, 'number')
        assert status == 409
        status, snapshot = raw_call('GET', '/_test/export')
        assert status == 200 and original.encode() in snapshot
        assert raw_call('POST', '/_test/import', snapshot, base=DEST)[0] == 204
        status, replay = raw_call('POST', '/reservations', numeric_body(equivalent), token, 'number', base=DEST)
        assert status == 200 and json.loads(replay) == json.loads(created)
        assert raw_call('POST', '/reservations', numeric_body(different), token, 'number', base=DEST)[0] == 409
    print('PASS huge positive/negative exponents, signed zero, 5000-digit exponent/coefficient, numeric equivalence, distinct retries and portable snapshots')


if __name__ == '__main__':
    run()
