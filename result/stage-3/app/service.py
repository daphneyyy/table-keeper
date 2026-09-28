"""One process owns state; every read and state transition shares one lock."""
import copy
import re
import secrets
from datetime import datetime, timedelta
from threading import RLock

from .auth import credentials, hash_password, verify
from .rules import (UTC, Error, booking, booking_fields, check_occupancy, clock, date_text, field,
                    hours, identifier, instant, json_equal, local_text, overlaps, party, require, selection)
from .state import empty_state, fixture, import_state, public
from .policies import configured, event, selected_terms, validate_policy


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
        remaining = (instant(record['starts_at']) - now).total_seconds()
        require(remaining > record['accepted_terms']['cancellation_cutoff_minutes'] * 60, 409, 'cutoff_passed')

    def changed(self, record, changes, now):
        if 'expected_revision' in changes:
            expected = changes['expected_revision']
            require(type(expected) is int and expected > 0)
            require(expected == record['revision'], 409, 'stale_revision')
        require(record['status'] != 'cancelled', 409, 'reservation_cancelled')
        self.cutoff(record, now)
        fields = booking_fields(record, changes)
        restaurant = self.restaurant(record['restaurant_id'])
        ids, _ = selection(restaurant, fields)
        local_text(fields['starts_at_local'])
        party(fields['party_size'])
        if (ids == record['table_ids'] and fields['starts_at_local'] == record['starts_at_local']
                and fields['party_size'] == record['party_size']):
            return record
        terms = selected_terms(self.state, restaurant, fields['starts_at_local'][:10])
        candidate = dict(record)
        candidate.pop('table_id', None)
        candidate.update(booking(configured(restaurant, terms), fields))
        candidate.update(accepted_terms=terms, revision=record['revision'] + 1)
        return candidate

    def availability(self, query):
        require('explain' not in query or query['explain'] == 'true')
        require(all(k in query for k in ('restaurant_id', 'date', 'party_size')))
        require(0 < len(query['restaurant_id']) <= 64)
        require(re.fullmatch('[0-9]+', query['party_size']) is not None)
        try:
            size = party(int(query['party_size']))
        except ValueError:
            raise Error() from None
        day = date_text(query['date'])
        restaurant = self.restaurant(query['restaurant_id'])
        terms = selected_terms(self.state, restaurant, query['date'])
        restaurant = configured(restaurant, terms)
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
                if 'explain' in query:
                    explanations = []
                    for table in restaurant['tables']:
                        candidate['table_ids'] = [table['id']]
                        capacity = table['capacity'] >= size
                        no_overlap = not any(r['status'] == 'confirmed' and overlaps(candidate, r)
                                             for r in self.state['reservations'].values())
                        explanations.append(dict(table_id=table['id'], policy_version=terms['policy_version'],
                                                 available=capacity and no_overlap,
                                                 rules=[dict(rule='capacity', holds=capacity),
                                                        dict(rule='no_overlap', holds=no_overlap)]))
                    slots[-1]['explain'] = explanations
        return dict(restaurant_id=restaurant['id'], date=query['date'], timezone=restaurant['timezone'], slots=slots)

    def create(self, body, uid):
        restaurant = self.restaurant(identifier(body, 'restaurant_id'))
        require('starts_at_local' in body)
        local_text(body['starts_at_local'])
        terms = selected_terms(self.state, restaurant, body['starts_at_local'][:10])
        candidate = booking(configured(restaurant, terms), body)
        ids = {r['reservation_id'] for r in self.state['reservations'].values()}
        ref = self.unique_id(self.state['reservations'])[:12].upper()
        while ref in self.state['reservations']:
            ref = secrets.token_hex(6).upper()
        candidate.update(reservation_id=self.unique_id(ids), reference=ref, user_id=uid,
                         status='confirmed', created_at=datetime.now(UTC).isoformat(), revision=1, accepted_terms=terms)
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

    def series_for(self, ref):
        for series in self.state['series'].values():
            for occurrence in series['occurrences']:
                if occurrence['reference'] == ref:
                    return series, occurrence
        return None, None

    def tick(self, rid):
        self.state['restaurant_revisions'][rid] += 1

    def commit_records(self, candidates):
        changed_restaurants, changed_series = set(), set()
        for candidate in candidates:
            ref = candidate['reference']
            before = self.state['reservations'].get(ref)
            if before and candidate['revision'] == before['revision']:
                continue
            self.state['reservations'][ref] = candidate
            if before is None:
                self.state['histories'][ref] = [event(candidate)]
            else:
                at = max(datetime.now(UTC), instant(self.state['histories'][ref][-1]['at'])).isoformat()
                self.state['histories'][ref].append(event(candidate, before, 'changed', at))
                series, occurrence = self.series_for(ref)
                if series:
                    occurrence['exception'] = True
                    changed_series.add(series['series_id'])
            changed_restaurants.add(candidate['restaurant_id'])
        for rid in changed_restaurants:
            self.tick(rid)
        for sid in changed_series:
            self.state['series'][sid]['revision'] += 1

    def series_response(self, series):
        return dict(series_id=series['series_id'], revision=series['revision'], interval_weeks=series['interval_weeks'],
                    occurrences=[dict(index=o['index'], reference=o['reference'], exception=o['exception'],
                                      reservation=public(self.state['reservations'][o['reference']]))
                                 for o in series['occurrences']])

    def adopt(self, body, uid):
        ref = identifier(body, 'anchor_reference')
        anchor = self.owned(ref, uid)
        require(anchor['status'] == 'confirmed', 409, 'reservation_cancelled')
        require(self.series_for(ref)[0] is None, 409, 'already_in_series')
        self.cutoff(anchor, datetime.now(UTC))
        count, interval = body.get('count'), body.get('interval_weeks')
        require(type(count) is int and 2 <= count <= 12)
        require(type(interval) is int and 1 <= interval <= 4)
        start = local_text(anchor['starts_at_local'])
        restaurant = self.restaurant(anchor['restaurant_id'])
        candidates = []
        occurrences = [dict(index=0, reference=ref, exception=False, scheduled_local=anchor['starts_at_local'])]
        ids = {r['reservation_id'] for r in self.state['reservations'].values()}
        refs = set(self.state['reservations'])
        for index in range(1, count):
            try:
                local = (start + timedelta(days=index * interval * 7)).isoformat(timespec='minutes')
            except OverflowError:
                raise Error() from None
            terms = selected_terms(self.state, restaurant, local[:10])
            fields = booking_fields(anchor, {'starts_at_local': local})
            candidate = booking(configured(restaurant, terms), fields)
            rid = self.unique_id(ids)
            ids.add(rid)
            reference = self.unique_id(refs)[:12].upper()
            while reference in refs:
                reference = secrets.token_hex(6).upper()
            refs.add(reference)
            candidate.update(reservation_id=rid, reference=reference, user_id=uid, status='confirmed',
                             created_at=datetime.now(UTC).isoformat(), revision=1, accepted_terms=terms)
            # Each index's ordinary booking error wins before examining the next.
            check_occupancy([candidate], list(self.state['reservations'].values()) + candidates)
            candidates.append(candidate)
            occurrences.append(dict(index=index, reference=reference, exception=False, scheduled_local=local))
        sid = self.unique_id(self.state['series'])
        series = dict(series_id=sid, user_id=uid, restaurant_id=anchor['restaurant_id'], revision=1,
                      interval_weeks=interval, occurrences=occurrences)
        self.commit_records(candidates)  # one restaurant increment, anchor untouched
        self.state['series'][sid] = series
        return self.series_response(series)

    def publish(self, path, body, uid):
        rid = path[len('/restaurants/'):-len('/policies')]
        restaurant = self.restaurant(rid)
        require(uid in restaurant['manager_user_ids'], 403, 'forbidden')
        policy = validate_policy(body, restaurant)
        policy['policy_version'] = len(self.state['policies'][rid]) + 1
        self.state['policies'][rid].append(policy)
        self.tick(rid)
        return policy

    def idempotent(self, method, path, body, uid, headers):
        key = headers.get('idempotency-key')
        require(key is not None and key != '', 400, 'missing_idempotency_key')
        require(len(key) <= 255)
        for receipt in self.state['receipts']:
            if (receipt['user_id'], receipt['method'], receipt['path'], receipt['key']) == (uid, method, path, key):
                require(json_equal(body, receipt['body']), 409, 'idempotency_key_reuse')
                return 200, copy.deepcopy(receipt['response'])
        if path in ('/reservations', '/reservation-moves'):
            candidates, response = self.create(body, uid) if path == '/reservations' else self.moves(body, uid)
            self.commit_records(candidates)
        elif path == '/series':
            response = self.adopt(body, uid)
        else:
            response = self.publish(path, body, uid)
        receipt = dict(schema_version=3, user_id=uid, method=method, path=path, key=key,
                       body=copy.deepcopy(body), response=copy.deepcopy(response))
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
            before = copy.deepcopy(self.state) if method != 'GET' else None
            try:
                status, response = self.dispatch(method, path, body, headers, query)
            except Exception:
                if before is not None:
                    self.state = before
                raise
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
        if method == 'GET' and re.fullmatch(r'/restaurants/.+/policies', path):
            rid = path[len('/restaurants/'):-len('/policies')]
            self.restaurant(rid)
            return 200, {'policies': self.state['policies'][rid]}
        if method == 'GET' and path.startswith('/restaurants/'):
            return 200, self.restaurant(path[len('/restaurants/'):])
        if method == 'GET' and path == '/availability':
            return 200, self.availability(query)
        private_read = re.fullmatch(r'/reservations/([^/]+)/(history|decision)', path) if method == 'GET' else None
        series_read = re.fullmatch(r'/series/([^/]+)', path) if method == 'GET' else None
        try:
            uid = self.caller(headers)
        except Error:
            if private_read or series_read:
                raise Error(404, 'not_found') from None
            raise
        if private_read:
            record = self.owned(private_read.group(1), uid)
            if private_read.group(2) == 'history':
                return 200, dict(reference=record['reference'], entries=self.state['histories'][record['reference']])
            return 200, {k: record[k] for k in ('reference', 'revision', 'accepted_terms')}
        if series_read:
            series = self.state['series'].get(series_read.group(1))
            require(series is not None and series['user_id'] == uid, 404, 'not_found')
            return 200, self.series_response(series)
        if method == 'POST' and (path in ('/reservations', '/reservation-moves', '/series')
                                 or re.fullmatch(r'/restaurants/.+/policies', path)):
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
                    record['revision'] += 1
                    at = max(datetime.now(UTC), instant(self.state['histories'][record['reference']][-1]['at'])).isoformat()
                    self.state['histories'][record['reference']].append(event(record, kind='cancelled', at=at))
                    self.tick(record['restaurant_id'])
                    series, _ = self.series_for(record['reference'])
                    if series:
                        series['revision'] += 1
                return 200, public(record)
            if method == 'PATCH' and not match.group(2):
                candidate = self.changed(record, body, datetime.now(UTC))
                check_occupancy([candidate], [r for ref, r in self.state['reservations'].items() if ref != record['reference']])
                self.commit_records([candidate])
                return 200, public(candidate)
        raise Error(404, 'not_found')
