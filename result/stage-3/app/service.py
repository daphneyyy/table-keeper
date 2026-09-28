"""One process owns state; every read and state transition shares one lock."""
import copy
import re
import secrets
from datetime import datetime
from threading import RLock

from .auth import credentials, hash_password, verify
from .rules import (UTC, Error, booking, booking_fields, check_occupancy, clock, date_text, field,
                    hours, identifier, instant, json_equal, overlaps, party, require)
from .state import empty_state, fixture, import_state, public


class Service:
    def __init__(self):
        self.lock = RLock()
        self.state = empty_state()
        self.generation = 0

    def replace(self, state):
        with self.lock:
            self.state = state
            self.generation += 1
        return 204, None

    def auth(self, path, body):
        signup = path == '/auth/signup'
        email, password = credentials(body, signup)
        if signup:
            hashed = hash_password(password)
            with self.lock:
                require(not any(u['email'] == email for u in self.state['users'].values()), 409, 'email_taken')
                uid = self.unique_id(self.state['users'])
                user = dict(id=uid, email=email, display_name=body['display_name'], password_hash=hashed)
                self.state['users'][uid] = user
                return 201, self.session(user)
        # Hashing does not block reads and bookings. Replacement while hashing
        # invalidates the observed account: retry against the current generation.
        while True:
            with self.lock:
                user = next((u for u in self.state['users'].values() if u['email'] == email), None)
                require(user is not None, 401, 'unauthenticated')
                generation = self.generation
            matches = verify(password, user['password_hash'])
            with self.lock:
                if generation != self.generation:
                    continue
                require(matches, 401, 'unauthenticated')
                return 200, self.session(user)

    @staticmethod
    def unique_id(existing):
        while True:
            value = secrets.token_hex(16)
            if value not in existing:
                return value

    def session(self, user):
        token = self.unique_id(self.state['sessions'])
        self.state['sessions'][token] = user['id']
        return dict(user_id=user['id'], display_name=user['display_name'], token=token)

    def caller(self, headers):
        auth = headers.get('authorization', '')
        match = re.fullmatch(r'Bearer ([^\s]+)', auth, re.IGNORECASE)
        uid = self.state['sessions'].get(match.group(1)) if match else None
        require(uid is not None, 401, 'unauthenticated')
        return uid

    def restaurant(self, rid):
        require(rid in self.state['restaurants'], 404, 'not_found')
        return self.state['restaurants'][rid]

    def owned(self, ref, uid):
        record = self.state['reservations'].get(ref)
        require(record is not None and record['user_id'] == uid, 404, 'not_found')
        return record

    def cutoff(self, record, now):
        restaurant = self.restaurant(record['restaurant_id'])
        remaining = (instant(record['starts_at']) - now).total_seconds()
        require(remaining > restaurant['cancellation_cutoff_minutes'] * 60, 409, 'cutoff_passed')

    def changed(self, record, changes, now):
        require(record['status'] != 'cancelled', 409, 'reservation_cancelled')
        self.cutoff(record, now)
        fields = booking_fields(record, changes)
        candidate = dict(record)
        candidate.pop('table_id', None)
        candidate.update(booking(self.restaurant(record['restaurant_id']), fields))
        return candidate

    def availability(self, query):
        require(all(k in query for k in ('restaurant_id', 'date', 'party_size')))
        require(0 < len(query['restaurant_id']) <= 64)
        require(re.fullmatch('[0-9]+', query['party_size']) is not None)
        try:
            size = party(int(query['party_size']))
        except ValueError:
            raise Error() from None
        day = date_text(query['date'])
        restaurant = self.restaurant(query['restaurant_id'])
        opening = hours(restaurant, day)
        slots = []
        if opening:
            for minute in range(clock(opening['opens']), clock(opening['closes']), restaurant['slot_minutes']):
                local = day.date().isoformat() + f'T{minute // 60:02d}:{minute % 60:02d}'
                # The same time validation is used even when no table can seat
                # this party: valid slots must appear with an empty table list.
                probe_restaurant = dict(restaurant, tables=[{'id': '_probe', 'capacity': size}])
                try:
                    candidate = booking(probe_restaurant, dict(table_id='_probe', party_size=size, starts_at_local=local))
                except Error as exc:
                    if exc.code in ('invalid_local_time', 'outside_opening_hours'):
                        continue
                    raise
                available, options = [], []
                tables = {t['id']: t for t in restaurant['tables']}
                choices = [[t['id']] for t in restaurant['tables']] + restaurant.get('combinable', [])
                for ids in choices:
                    candidate['table_ids'] = ids
                    capacity = sum(tables[tid]['capacity'] for tid in ids)
                    if capacity >= size and not any(r['status'] == 'confirmed' and overlaps(candidate, r)
                                                   for r in self.state['reservations'].values()):
                        options.append(dict(table_ids=list(ids), capacity=capacity))
                        if len(ids) == 1:
                            available.append(ids[0])
                slots.append(dict(starts_at_local=local, starts_at=candidate['starts_at'],
                                  available_table_ids=available, available_options=options))
        return dict(restaurant_id=restaurant['id'], date=query['date'], timezone=restaurant['timezone'], slots=slots)

    def create(self, body, uid):
        restaurant = self.restaurant(identifier(body, 'restaurant_id'))
        candidate = booking(restaurant, body)
        ids = {r['reservation_id'] for r in self.state['reservations'].values()}
        ref = self.unique_id(self.state['reservations'])[:12].upper()
        while ref in self.state['reservations']:
            ref = secrets.token_hex(6).upper()
        candidate.update(reservation_id=self.unique_id(ids), reference=ref, user_id=uid,
                         status='confirmed', created_at=datetime.now(UTC).isoformat())
        check_occupancy([candidate], self.state['reservations'].values())
        return [candidate], public(candidate)

    def moves(self, body, uid):
        moves = body.get('moves')
        require(type(moves) is list and 1 <= len(moves) <= 8)
        refs = []
        for item in moves:
            require(type(item) is dict and type(item.get('reference')) is str)
            require(0 < len(item['reference']) <= 64 and item['reference'] not in refs)
            refs.append(item['reference'])
        now = datetime.now(UTC)
        candidates = []
        restaurant_id = None
        for item in moves:
            record = self.owned(item['reference'], uid)
            require(restaurant_id is None or restaurant_id == record['restaurant_id'])
            restaurant_id = record['restaurant_id']
            candidates.append(self.changed(record, item, now))
        check_occupancy(candidates, [r for ref, r in self.state['reservations'].items() if ref not in refs])
        return candidates, {'reservations': [public(r) for r in candidates]}

    def idempotent(self, method, path, body, uid, headers):
        key = headers.get('idempotency-key')
        require(key is not None and key != '', 400, 'missing_idempotency_key')
        require(len(key) <= 255)
        for receipt in self.state['receipts']:
            if (receipt['user_id'], receipt['method'], receipt['path'], receipt['key']) == (uid, method, path, key):
                require(json_equal(body, receipt['body']), 409, 'idempotency_key_reuse')
                return 200, copy.deepcopy(receipt['response'])
        candidates, response = self.create(body, uid) if path == '/reservations' else self.moves(body, uid)
        receipt = dict(schema_version=2, user_id=uid, method=method, path=path, key=key,
                       body=copy.deepcopy(body), response=copy.deepcopy(response))
        # All fallible domain validation precedes the atomic commit below.
        for candidate in candidates:
            self.state['reservations'][candidate['reference']] = candidate
        self.state['receipts'].append(receipt)
        return 201, response

    def handle(self, method, path, body, headers, query):
        if method == 'POST' and path == '/_test/reset':
            return self.replace(fixture(body))
        if method == 'POST' and path == '/_test/import':
            return self.replace(import_state(body))
        if method == 'POST' and path in ('/auth/signup', '/auth/login'):
            return self.auth(path, body)
        with self.lock:
            status, response = self.dispatch(method, path, body, headers, query)
            # Detach under the lock before the HTTP layer serializes this value.
            return status, copy.deepcopy(response)

    def dispatch(self, method, path, body, headers, query):
        if method == 'GET' and path == '/health':
            return 200, {'status': 'ok'}
        if method == 'GET' and path == '/_test/export':
            return 200, {'track': 'tablekeeper', 'format_version': 1, 'state': self.state}
        if method == 'GET' and path == '/restaurants':
            return 200, {'restaurants': [{k: r[k] for k in ('id', 'name', 'timezone')}
                                          for r in self.state['restaurants'].values()]}
        if method == 'GET' and path.startswith('/restaurants/'):
            return 200, self.restaurant(path[len('/restaurants/'):])
        if method == 'GET' and path == '/availability':
            return 200, self.availability(query)
        uid = self.caller(headers)
        if method == 'POST' and path in ('/reservations', '/reservation-moves'):
            return self.idempotent(method, path, body, uid, headers)
        if method == 'GET' and path == '/reservations':
            records = [r for r in self.state['reservations'].values() if r['user_id'] == uid]
            records.sort(key=lambda r: instant(r['starts_at']), reverse=True)
            return 200, {'reservations': [public(r) for r in records]}
        match = re.fullmatch(r'/reservations/([^/]+)(/cancel)?', path)
        if match:
            record = self.owned(match.group(1), uid)
            if method == 'GET' and not match.group(2):
                return 200, public(record)
            if method == 'POST' and match.group(2):
                if record['status'] != 'cancelled':
                    self.cutoff(record, datetime.now(UTC))
                    record['status'] = 'cancelled'
                return 200, public(record)
            if method == 'PATCH' and not match.group(2):
                candidate = self.changed(record, body, datetime.now(UTC))
                check_occupancy([candidate], [r for ref, r in self.state['reservations'].items() if ref != record['reference']])
                self.state['reservations'][record['reference']] = candidate
                return 200, public(candidate)
        raise Error(404, 'not_found')
