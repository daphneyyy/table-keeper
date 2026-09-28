"""Serializable state, validated snapshots, and atomic replacement helpers."""
import copy
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .auth import credentials, hash_password, validate_hash
from .rules import (UTC, WEEKDAYS, Error, booking, booking_fields, check_occupancy, clock, field,
                    identifier, instant, positive, require)


def empty_state():
    return {'schema_version': 2, 'users': {}, 'restaurants': {}, 'reservations': {},
            'sessions': {}, 'receipts': []}


def validate_restaurant(raw):
    require(type(raw) is dict, 400, 'malformed_request')
    result = {key: field(raw, key) for key in ('name', 'timezone')}
    result['id'] = identifier(raw, 'id')
    try:
        ZoneInfo(result['timezone'])
    except (ZoneInfoNotFoundError, ValueError):
        raise Error() from None
    for key in ('slot_minutes', 'reservation_duration_minutes', 'cancellation_cutoff_minutes'):
        result[key] = positive(raw, key, 0 if key == 'cancellation_cutoff_minutes' else 1)
    result['opening_hours'] = []
    seen = set()
    for day in field(raw, 'opening_hours', list):
        require(type(day) is dict, 400, 'malformed_request')
        weekday = field(day, 'weekday')
        require(weekday in WEEKDAYS and weekday not in seen)
        seen.add(weekday)
        opens, closes = field(day, 'opens'), field(day, 'closes')
        require(clock(opens) < clock(closes))
        result['opening_hours'].append(dict(weekday=weekday, opens=opens, closes=closes))
    result['tables'] = []
    seen = set()
    for table in field(raw, 'tables', list):
        require(type(table) is dict, 400, 'malformed_request')
        tid = identifier(table, 'id')
        require(tid not in seen)
        seen.add(tid)
        result['tables'].append(dict(id=tid, label=field(table, 'label'), capacity=positive(table, 'capacity')))
    result['combinable'] = []
    pairs = set()
    for pair in field(raw, 'combinable', list) if 'combinable' in raw else []:
        require(type(pair) is list, 400, 'malformed_request')
        require(len(pair) == 2)
        for tid in pair:
            identifier({'id': tid}, 'id')
        require(pair[0] != pair[1] and all(tid in seen for tid in pair))
        require(frozenset(pair) not in pairs)
        pairs.add(frozenset(pair))
        result['combinable'].append(list(pair))
    return result


def reference(value):
    require(type(value) is str and re.fullmatch('[A-Z0-9]{6,12}', value) is not None)
    return value


def public(record):
    return {key: value for key, value in record.items() if key != 'user_id'}


def fixture(body):
    state = empty_state()
    emails = set()
    for user in field(body, 'users', list):
        require(type(user) is dict, 400, 'malformed_request')
        uid = identifier(user, 'id')
        email, password = credentials(user)
        require(re.fullmatch(r'[^\s@]+@[^\s@]+', email) is not None)
        field(user, 'display_name')
        require(uid not in state['users'] and email not in emails)
        emails.add(email)
        state['users'][uid] = dict(id=uid, email=email, display_name=user['display_name'],
                                   password_hash=hash_password(password))
    for raw in field(body, 'restaurants', list):
        restaurant = validate_restaurant(raw)
        require(restaurant['id'] not in state['restaurants'])
        state['restaurants'][restaurant['id']] = restaurant
    ids = set()
    for raw in field(body, 'reservations', list):
        require(type(raw) is dict, 400, 'malformed_request')
        rid, uid = identifier(raw, 'id'), identifier(raw, 'user_id')
        ref = reference(field(raw, 'reference'))
        restaurant_id = identifier(raw, 'restaurant_id')
        require(restaurant_id in state['restaurants'] and uid in state['users'])
        require(ref not in state['reservations'] and rid not in ids)
        ids.add(rid)
        record = booking(state['restaurants'][restaurant_id], raw)
        status = field(raw, 'status') if 'status' in raw else 'confirmed'
        require(status in ('confirmed', 'cancelled'))
        record.update(reservation_id=rid, reference=ref, user_id=uid, status=status,
                      created_at=datetime.now(UTC).isoformat())
        check_occupancy([record], state['reservations'].values())
        state['reservations'][ref] = record
    return state


def validate_response(raw, state, owner, legacy=False):
    require(type(raw) is dict)
    keys = {'reservation_id', 'reference', 'restaurant_id', 'party_size',
            'status', 'starts_at_local', 'starts_at', 'ends_at', 'created_at'}
    if legacy:
        keys.add('table_id')
    else:
        ids = field(raw, 'table_ids', list)
        keys.add('table_ids')
        if len(ids) == 1:
            keys.add('table_id')
    require(set(raw) == keys)
    identifier(raw, 'reservation_id')
    ref = reference(field(raw, 'reference'))
    require(ref in state['reservations'])
    current = state['reservations'][ref]
    require(current['user_id'] == owner and current['reservation_id'] == raw['reservation_id'])
    rid = identifier(raw, 'restaurant_id')
    require(rid in state['restaurants'] and rid == current['restaurant_id'])
    computed = booking(state['restaurants'][rid], booking_fields(raw))
    if legacy:
        computed.pop('table_ids')
    require(all(raw.get(k) == v for k, v in computed.items()))
    require(raw.get('status') in ('confirmed', 'cancelled'))
    instant(field(raw, 'created_at'))
    require(raw['created_at'] == current['created_at'])


def import_state(body):
    # Imported data is untrusted. All schema and referential checks complete on a
    # private candidate; no destination state is touched until this returns.
    try:
        require(body.get('track') == 'tablekeeper' and type(body.get('format_version')) is int
                and body['format_version'] == 1)
        state = copy.deepcopy(field(body, 'state', dict))
        require(set(state) == set(empty_state()) and type(state['schema_version']) is int
                and state['schema_version'] in (1, 2))
        legacy = state['schema_version'] == 1
        for name in ('users', 'restaurants', 'reservations', 'sessions'):
            require(type(state[name]) is dict)
        require(type(state['receipts']) is list)
        if legacy:
            # Live records gain the new shape. Historical request/response JSON
            # is never rewritten: even fields unknown to stage 1 remain intact.
            for restaurant in state['restaurants'].values():
                require(type(restaurant) is dict and 'combinable' not in restaurant)
                restaurant['combinable'] = []
            for record in state['reservations'].values():
                require(type(record) is dict and 'table_ids' not in record)
                record['table_ids'] = [identifier(record, 'table_id')]
            for receipt in state['receipts']:
                require(type(receipt) is dict and 'schema_version' not in receipt)
                receipt['schema_version'] = 1
            state['schema_version'] = 2
        emails = set()
        for uid, user in state['users'].items():
            require(type(user) is dict and identifier(user, 'id') == uid)
            email = field(user, 'email')
            require(re.fullmatch(r'[^\s@]+@[^\s@]+', email) is not None and email not in emails)
            emails.add(email)
            field(user, 'display_name')
            require(set(user) == {'id', 'email', 'display_name', 'password_hash'})
            validate_hash(user['password_hash'])
        for rid, restaurant in state['restaurants'].items():
            require(validate_restaurant(restaurant) == restaurant and restaurant['id'] == rid)
        for token, uid in state['sessions'].items():
            require(type(token) is str and len(token) > 0 and type(uid) is str and uid in state['users'])
        ids = set()
        for ref, record in state['reservations'].items():
            require(type(record) is dict and record.get('reference') == ref)
            uid = identifier(record, 'user_id')
            require(uid in state['users'])
            validate_response(public(record), state, uid)
            require(record['reservation_id'] not in ids)
            ids.add(record['reservation_id'])
        check_occupancy(list(state['reservations'].values()), [])
        receipt_keys = set()
        for receipt in state['receipts']:
            require(type(receipt) is dict and set(receipt) == {'schema_version', 'user_id', 'method', 'path', 'key', 'body', 'response'})
            require(type(receipt['schema_version']) is int and receipt['schema_version'] in (1, 2))
            old_receipt = receipt['schema_version'] == 1
            uid = identifier(receipt, 'user_id')
            require(uid in state['users'] and receipt['method'] == 'POST'
                    and receipt['path'] in ('/reservations', '/reservation-moves'))
            key = field(receipt, 'key')
            require(1 <= len(key) <= 255 and type(receipt['body']) is dict)
            scope = (uid, receipt['method'], receipt['path'], key)
            require(scope not in receipt_keys)
            receipt_keys.add(scope)
            response = receipt['response']
            if receipt['path'] == '/reservations':
                validate_response(response, state, uid, old_receipt)
                require(response['status'] == 'confirmed')
                rid = identifier(receipt['body'], 'restaurant_id')
                require(rid == response['restaurant_id'])
                request = receipt['body']
                if old_receipt:
                    request = {k: v for k, v in request.items() if k != 'table_ids'}
                proposed = booking(state['restaurants'][rid], request)
                if old_receipt:
                    proposed.pop('table_ids')
                require(all(response[k] == v for k, v in proposed.items()))
            else:
                require(type(response) is dict and set(response) == {'reservations'})
                records = field(response, 'reservations', list)
                require(1 <= len(records) <= 8)
                moves = receipt['body'].get('moves')
                require(type(moves) is list and len(moves) == len(records))
                seen = set()
                restaurants = set()
                for move, record in zip(moves, records):
                    validate_response(record, state, uid, old_receipt)
                    require(record['status'] == 'confirmed' and type(move) is dict
                            and move.get('reference') == record['reference'])
                    changes = {k: v for k, v in move.items() if not (old_receipt and k == 'table_ids')}
                    proposed = booking_fields(record, changes)
                    computed = booking(state['restaurants'][record['restaurant_id']], proposed)
                    if old_receipt:
                        computed.pop('table_ids')
                    require(all(record[k] == v for k, v in computed.items()))
                    require(record['reference'] not in seen)
                    seen.add(record['reference'])
                    restaurants.add(record['restaurant_id'])
                require(len(restaurants) == 1)
                check_occupancy([dict(r, table_ids=[r['table_id']]) if old_receipt else r for r in records], [])
        return state
    except (Error, KeyError, TypeError, ValueError, OverflowError):
        raise Error() from None
