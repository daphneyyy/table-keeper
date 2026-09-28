"""Independent disposable-instance contract probes; never prints credentials/exports."""
import copy
import json
import sys

import httpx

c = httpx.Client(base_url=sys.argv[1], timeout=10)
fixture = {
    'users': [{'id': 'u', 'email': 'review@example.test', 'password': 'review-password', 'display_name': 'Reviewer'}],
    'restaurants': [{'id': 'r', 'name': 'Review restaurant', 'timezone': 'Europe/Berlin',
                     'slot_minutes': 30, 'reservation_duration_minutes': 90, 'cancellation_cutoff_minutes': 0,
                     'opening_hours': [{'weekday': day, 'opens': '18:00', 'closes': '23:00'}
                                       for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']],
                     'tables': [{'id': 't', 'label': 'Window', 'capacity': 4}]}],
    'reservations': [],
}

def request(method, path, **kwargs):
    return c.request(method, path, **kwargs)

def reset():
    assert c.post('/_test/reset', json=fixture).status_code == 204

def login():
    response = c.post('/auth/login', json={'email': 'review@example.test', 'password': 'review-password'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}

def show(name, response):
    data = response.json()
    print(name, response.status_code, data.get('error', {}).get('code', 'non-error-envelope'))
    return response

reset()
for path in ['/restaurants', '/restaurants/r', '/availability?restaurant_id=r&date=2030-01-01&party_size=2']:
    r = c.get(path)
    assert r.status_code == 200 and r.headers['content-type'] == 'application/json; charset=utf-8'
h = login()
h2 = login()
assert c.get('/reservations', headers=h).status_code == c.get('/reservations', headers=h2).status_code == 200
body = {'restaurant_id': 'r', 'table_id': 't', 'party_size': 2, 'starts_at_local': '2030-01-01T18:00'}
headers = dict(h, **{'Idempotency-Key': 'review-key'})
r = c.post('/reservations', json=body, headers=headers)
assert r.status_code == 201
original = r.json()
ref = original['reference']
assert c.patch('/reservations/' + ref, json={'party_size': 3}, headers=h).status_code == 200
assert c.post('/reservations/' + ref + '/cancel', headers=h).status_code == 200
assert c.post('/reservations/' + ref + '/cancel', headers=h).status_code == 200
r = c.post('/reservations', json=body, headers=headers)
assert r.status_code == 200 and r.json() == original
snapshot = c.get('/_test/export').json()
reset()
assert c.get('/reservations', headers=h).status_code == 401
assert c.post('/_test/import', json=snapshot).status_code == 204
assert c.get('/reservations', headers=h).status_code == c.get('/reservations', headers=h2).status_code == 200
r = c.post('/reservations', json=body, headers=headers)
assert r.status_code == 200 and r.json() == original
invalid = copy.deepcopy(snapshot)
invalid['state']['schema_version'] = 99
assert c.post('/_test/import', json=invalid).status_code == 422
assert c.get('/reservations/' + ref, headers=h).json()['status'] == 'cancelled'
assert c.post('/reservations', json=dict(body, party_size=False), headers=headers).json()['error']['code'] == 'idempotency_key_reuse'
print('PASS public browsing/charset, simultaneous tokens, amend/cancel original replay, reset invalidation, import restoration and invalid-import rollback')

# An ignored JSON number must not corrupt successful receipt persistence.
reset()
h = login()
headers = dict(h, **{'Idempotency-Key': 'large-ignored-number'})
raw = json.dumps(body)[:-1] + ', "ignored": 1e400}'
created = show('large ignored number create', c.post('/reservations', content=raw, headers=headers))
assert created.status_code == 201
exported = show('export after large ignored number', c.get('/_test/export'))
assert exported.status_code == 200
changed = json.dumps(body)[:-1] + ', "ignored": 2e400}'
different = show('different large ignored number same key', c.post('/reservations', content=changed, headers=headers))
assert different.status_code == 409 and different.json()['error']['code'] == 'idempotency_key_reuse'
reset()
# Preserve exact export bytes: the client's default JSON decoder is itself lossy.
assert c.post('/_test/import', content=exported.content, headers={'Content-Type': 'application/json'}).status_code == 204
replayed = c.post('/reservations', content=raw, headers=headers)
assert replayed.status_code == 200 and replayed.json() == created.json()
assert c.post('/reservations', content=changed, headers=headers).status_code == 409
print('PASS large-number export/import retains original receipt and numeric distinction')

reset()
unsupported = show('unsupported TRACE method', request('TRACE', '/health'))
assert unsupported.status_code == 405 and unsupported.json()['error']['message']
early = show('year 0001 availability', c.get('/availability', params={'restaurant_id': 'r', 'date': '0001-01-01', 'party_size': '2'}))
assert early.status_code == 200 and early.json()['slots']
early_local = early.json()['slots'][0]['starts_at_local']
assert early_local == '0001-01-01T18:00'
h = login()
early_create = c.post('/reservations', json=dict(body, starts_at_local=early_local), headers=dict(h, **{'Idempotency-Key': 'early-year'}))
assert early_create.status_code == 201
assert early_create.json()['starts_at_local'] == early_local
print('PASS early-year availability can be booked unchanged')
