"""Versioned snapshots: legacy validation, atomic migration, current invariants."""
import copy
import re
from datetime import timedelta

from . import legacy_state
from .policies import TERM_FIELDS, base_terms, configured, initialize_records, validate_policy
from .rules import (Error, booking, booking_fields, check_occupancy, field, identifier,
                    instant, json_equal, local_text, require)

public = legacy_state.public
reference = legacy_state.reference


def empty_state():
    state = legacy_state.empty_state()
    state['schema_version'] = 3
    initialize_records(state)
    return state


def managers(raw, users):
    values = field(raw, 'manager_user_ids', list) if 'manager_user_ids' in raw else []
    for uid in values:
        identifier({'id': uid}, 'id')
        require(uid in users)
    require(len(set(values)) == len(values))
    return list(values)


def fixture(body):
    state = legacy_state.fixture(body)
    state['schema_version'] = 3
    initialize_records(state)
    for raw in body['restaurants']:
        state['restaurants'][raw['id']]['manager_user_ids'] = managers(raw, state['users'])
    return state


def validate_terms(terms, restaurant, policies):
    require(type(terms) is dict and set(terms) == {'policy_version', *TERM_FIELDS})
    version = field(terms, 'policy_version', int)
    require(0 <= version <= len(policies))
    expected = base_terms(restaurant) if version == 0 else {
        k: policies[version - 1][k] for k in ('policy_version', *TERM_FIELDS)}
    require(json_equal(terms, expected))


def validate_record(raw, state, uid, version=3):
    require(type(raw) is dict)
    keys = {'reservation_id', 'reference', 'restaurant_id', 'party_size', 'status',
            'starts_at_local', 'starts_at', 'ends_at', 'created_at'}
    if version == 1:
        keys.add('table_id')
    else:
        ids = field(raw, 'table_ids', list)
        keys.add('table_ids')
        if len(ids) == 1:
            keys.add('table_id')
    if version == 3:
        keys.update(('revision', 'accepted_terms'))
        require(type(raw.get('revision')) is int and raw['revision'] > 0)
    require(set(raw) == keys)
    ref = reference(field(raw, 'reference'))
    require(ref in state['reservations'])
    current = state['reservations'][ref]
    if version == 3:
        require(raw['revision'] <= current['revision'])
        history = state['histories'][ref]
        require(type(history) is list and len(history) >= raw['revision'])
        require(json_equal(raw['accepted_terms'], history[raw['revision'] - 1]['accepted_terms']))
    require(current['user_id'] == uid and identifier(raw, 'reservation_id') == current['reservation_id'])
    rid = identifier(raw, 'restaurant_id')
    require(rid in state['restaurants'] and rid == current['restaurant_id'])
    restaurant = state['restaurants'][rid]
    terms = raw['accepted_terms'] if version == 3 else base_terms(restaurant)
    validate_terms(terms, restaurant, state['policies'][rid])
    computed = booking(configured(restaurant, terms), booking_fields(raw))
    if version == 1:
        computed.pop('table_ids')
    require(all(raw.get(k) == v for k, v in computed.items()))
    require(raw.get('status') in ('confirmed', 'cancelled'))
    instant(field(raw, 'created_at'))
    require(raw['created_at'] == current['created_at'])


def validate_history(state, ref):
    record = state['reservations'][ref]
    entries = state['histories'][ref]
    require(type(entries) is list and len(entries) == record['revision'])
    previous_at = None
    values = {}
    for index, item in enumerate(entries, 1):
        require(type(item) is dict and set(item) == {'seq', 'at', 'event', 'changes', 'revision', 'accepted_terms'})
        require(type(item['seq']) is int and item['seq'] == index
                and type(item['revision']) is int and item['revision'] == index)
        at = instant(item['at'])
        require(previous_at is None or at >= previous_at)
        previous_at = at
        rid = record['restaurant_id']
        validate_terms(item['accepted_terms'], state['restaurants'][rid], state['policies'][rid])
        kind = item['event']
        require(kind == 'created' if index == 1 else kind in ('changed', 'cancelled'))
        changes = field(item, 'changes', list)
        if kind == 'cancelled':
            require(index == len(entries) and record['status'] == 'cancelled' and changes == [])
        else:
            require(1 <= len(changes) <= 3)
            order = []
            for change in changes:
                require(type(change) is dict and set(change) == {'field', 'from', 'to'})
                name = change['field']
                require(name in ('table_id', 'table_ids', 'starts_at_local', 'party_size'))
                rank = {'table_id': 0, 'table_ids': 0, 'starts_at_local': 1, 'party_size': 2}[name]
                require(not order or rank > order[-1])
                order.append(rank)
                if name in ('table_id', 'table_ids'):
                    before = values.get('table_ids')
                    previous = before[0] if name == 'table_id' and before else before
                    require(change['from'] == previous)
                    values['table_ids'] = [change['to']] if name == 'table_id' else change['to']
                else:
                    require(change['from'] == values.get(name))
                    values[name] = change['to']
                if kind == 'changed':
                    require(change['from'] != change['to'])
            if kind == 'created':
                require(order == [0, 1, 2] and all(c['from'] is None for c in changes))
            booking(configured(state['restaurants'][rid], item['accepted_terms']), values)
    require(all(values.get(k) == record[k] for k in ('table_ids', 'starts_at_local', 'party_size')))
    require(entries[-1]['accepted_terms'] == record['accepted_terms'])


def validate_series_response(response, state, uid):
    require(type(response) is dict and set(response) == {'series_id', 'revision', 'interval_weeks', 'occurrences'})
    sid = identifier(response, 'series_id')
    require(sid in state['series'] and state['series'][sid]['user_id'] == uid)
    current = state['series'][sid]
    require(type(response['revision']) is int and 1 <= response['revision'] <= current['revision'])
    require(type(response['interval_weeks']) is int and response['interval_weeks'] == current['interval_weeks'])
    items = field(response, 'occurrences', list)
    require(len(items) == len(current['occurrences']))
    for i, item in enumerate(items):
        require(type(item) is dict and set(item) == {'index', 'reference', 'exception', 'reservation'})
        require(type(item['index']) is int and item['index'] == i and type(item['exception']) is bool)
        require(item['reference'] == current['occurrences'][i]['reference'])
        require(item['reservation']['reference'] == item['reference'])
        validate_record(item['reservation'], state, uid)


def import_state(body):
    try:
        raw = field(body, 'state', dict)
        if type(raw.get('schema_version')) is int and raw['schema_version'] in (1, 2):
            state = legacy_state.import_state(body)
            state['schema_version'] = 3
            initialize_records(state)
            return state
        require(body.get('track') == 'tablekeeper' and type(body.get('format_version')) is int
                and body['format_version'] == 1)
        state = copy.deepcopy(raw)
        require(set(state) == set(empty_state()) and type(state['schema_version']) is int and state['schema_version'] == 3)
        for name in ('users', 'restaurants', 'reservations', 'sessions', 'policies', 'histories', 'series', 'restaurant_revisions'):
            require(type(state[name]) is dict)
        require(type(state['receipts']) is list)
        skeleton = {k: copy.deepcopy(state[k]) for k in ('users', 'restaurants', 'sessions')}
        skeleton.update(schema_version=2, reservations={}, receipts=[])
        for restaurant in skeleton['restaurants'].values():
            restaurant.pop('manager_user_ids', None)
        legacy_state.import_state(dict(track='tablekeeper', format_version=1, state=skeleton))
        require(set(state['policies']) == set(state['restaurants']) == set(state['restaurant_revisions']))
        for rid, restaurant in state['restaurants'].items():
            require('manager_user_ids' in restaurant)
            managers(restaurant, state['users'])
            revision = state['restaurant_revisions'][rid]
            require(type(revision) is int and revision >= 0)
            policies = state['policies'][rid]
            require(type(policies) is list)
            for index, policy in enumerate(policies, 1):
                require(type(policy) is dict and type(policy.get('policy_version')) is int and policy['policy_version'] == index)
                expected = validate_policy(policy, restaurant)
                expected['policy_version'] = index
                require(policy == expected)
        ids = set()
        require(set(state['histories']) == set(state['reservations']))
        for ref, record in state['reservations'].items():
            require(type(record) is dict and record.get('reference') == ref)
            uid = identifier(record, 'user_id')
            require(uid in state['users'])
            validate_record(public(record), state, uid)
            require(record['reservation_id'] not in ids)
            ids.add(record['reservation_id'])
            validate_history(state, ref)
        check_occupancy(list(state['reservations'].values()), [])
        adopted = set()
        for sid, series in state['series'].items():
            require(type(series) is dict and set(series) == {'series_id', 'user_id', 'restaurant_id', 'revision', 'interval_weeks', 'occurrences'})
            require(identifier(series, 'series_id') == sid and series['user_id'] in state['users']
                    and series['restaurant_id'] in state['restaurants'])
            require(type(series['revision']) is int and series['revision'] >= 1)
            require(type(series['interval_weeks']) is int and 1 <= series['interval_weeks'] <= 4)
            items = field(series, 'occurrences', list)
            require(2 <= len(items) <= 12)
            start = None
            for index, item in enumerate(items):
                require(type(item) is dict and set(item) == {'index', 'reference', 'exception', 'scheduled_local'})
                require(type(item['index']) is int and item['index'] == index and type(item['exception']) is bool)
                ref = item['reference']
                require(ref in state['reservations'] and ref not in adopted)
                adopted.add(ref)
                record = state['reservations'][ref]
                require(record['user_id'] == series['user_id'] and record['restaurant_id'] == series['restaurant_id'])
                local = local_text(item['scheduled_local'])
                start = local if start is None else start
                require(local == start + timedelta(days=index * series['interval_weeks'] * 7))
                if not item['exception']:
                    require(record['starts_at_local'] == item['scheduled_local'])
        scopes = set()
        for receipt in state['receipts']:
            require(type(receipt) is dict and set(receipt) == {'schema_version', 'user_id', 'method', 'path', 'key', 'body', 'response'})
            version = receipt['schema_version']
            require(type(version) is int and version in (1, 2, 3))
            uid = identifier(receipt, 'user_id')
            require(uid in state['users'] and receipt['method'] == 'POST')
            key, path = field(receipt, 'key'), field(receipt, 'path')
            require(1 <= len(key) <= 255 and type(receipt['body']) is dict)
            scope = (uid, path, key)
            require(scope not in scopes)
            scopes.add(scope)
            response, request = receipt['response'], receipt['body']
            if path in ('/reservations', '/reservation-moves'):
                if path == '/reservations':
                    records, requests = [response], [request]
                else:
                    require(type(response) is dict and set(response) == {'reservations'})
                    records, requests = field(response, 'reservations', list), field(request, 'moves', list)
                    require(1 <= len(records) <= 8 and len(records) == len(requests))
                seen, restaurants = set(), set()
                for record, item in zip(records, requests):
                    validate_record(record, state, uid, version)
                    require(record['status'] == 'confirmed' and type(item) is dict)
                    require(record['reference'] not in seen)
                    seen.add(record['reference'])
                    rid = record['restaurant_id']
                    restaurants.add(rid)
                    changes = {k: v for k, v in item.items() if not (version == 1 and k == 'table_ids')}
                    if path == '/reservations':
                        require(identifier(item, 'restaurant_id') == rid)
                        fields = changes
                    else:
                        require(item.get('reference') == record['reference'])
                        if version == 3 and 'expected_revision' in item:
                            expected_revision = item['expected_revision']
                            require(type(expected_revision) is int and expected_revision > 0
                                    and record['revision'] in (expected_revision, expected_revision + 1))
                        fields = booking_fields(record, changes)
                    terms = record['accepted_terms'] if version == 3 else base_terms(state['restaurants'][rid])
                    computed = booking(configured(state['restaurants'][rid], terms), fields)
                    if version == 1:
                        computed.pop('table_ids')
                    require(all(record[k] == v for k, v in computed.items()))
                require(len(restaurants) == 1)
                check_occupancy([dict(r, table_ids=[r['table_id']]) if version == 1 else r for r in records], [])
            elif path == '/series' and version == 3:
                validate_series_response(response, state, uid)
                require(response['revision'] == 1 and request.get('anchor_reference') == response['occurrences'][0]['reference'])
                require(all(o['exception'] is False and o['reservation']['status'] == 'confirmed'
                            for o in response['occurrences']))
                require(all(o['reservation']['revision'] == 1 for o in response['occurrences'][1:]))
                require(type(request.get('count')) is int and request['count'] == len(response['occurrences']))
                require(type(request.get('interval_weeks')) is int and request['interval_weeks'] == response['interval_weeks'])
            elif version == 3 and re.fullmatch(r'/restaurants/.+/policies', path):
                rid = path[len('/restaurants/'):-len('/policies')]
                require(rid in state['restaurants'] and uid in state['restaurants'][rid]['manager_user_ids'])
                policy = validate_policy(request, state['restaurants'][rid])
                version_number = field(response, 'policy_version', int)
                require(1 <= version_number <= len(state['policies'][rid]))
                policy['policy_version'] = version_number
                require(response == policy == state['policies'][rid][version_number - 1])
            else:
                raise Error()
        return state
    except (Error, KeyError, TypeError, ValueError, OverflowError, AttributeError):
        raise Error() from None
