"""Immutable dated policies, accepted terms, and truthful ordered events."""
import copy

from .rules import Error, WEEKDAYS, clock, date_text, field, require

TERM_FIELDS = ('slot_minutes', 'reservation_duration_minutes', 'cancellation_cutoff_minutes',
               'opening_hours', 'capacities')


def base_terms(restaurant):
    return dict(policy_version=0, **{k: copy.deepcopy(restaurant[k]) for k in TERM_FIELDS if k != 'capacities'},
                capacities={t['id']: t['capacity'] for t in restaurant['tables']})


def selected_terms(state, restaurant, local_date):
    eligible = [p for p in state['policies'][restaurant['id']] if p['effective_from'] <= local_date]
    if not eligible:
        return base_terms(restaurant)
    policy = max(eligible, key=lambda p: (p['effective_from'], p['policy_version']))
    return {k: copy.deepcopy(policy[k]) for k in ('policy_version', *TERM_FIELDS)}


def configured(restaurant, terms):
    result = copy.deepcopy(restaurant)
    for key in TERM_FIELDS:
        if key != 'capacities':
            result[key] = copy.deepcopy(terms[key])
    for table in result['tables']:
        table['capacity'] = terms['capacities'][table['id']]
    return result


def validate_policy(body, restaurant):
    try:
        effective = field(body, 'effective_from')
        date_text(effective)
        result = {'effective_from': effective}
        for key, low, high in [('slot_minutes', 1, 1440), ('reservation_duration_minutes', 1, 1440),
                               ('cancellation_cutoff_minutes', 0, 10080)]:
            value = field(body, key, int)
            require(low <= value <= high)
            result[key] = value
        result['opening_hours'] = []
        seen = set()
        for raw in field(body, 'opening_hours', list):
            require(type(raw) is dict)
            weekday = field(raw, 'weekday')
            require(weekday in WEEKDAYS and weekday not in seen)
            seen.add(weekday)
            opens, closes = field(raw, 'opens'), field(raw, 'closes')
            require(clock(opens) < clock(closes))
            result['opening_hours'].append(dict(weekday=weekday, opens=opens, closes=closes))
        capacities = field(body, 'capacities', dict)
        require(set(capacities) == {t['id'] for t in restaurant['tables']})
        require(all(type(v) is int and 1 <= v <= 100 for v in capacities.values()))
        result['capacities'] = dict(capacities)
        return result
    except (Error, TypeError, ValueError):
        raise Error() from None


def event(record, before=None, kind='created', at=None):
    changes = []
    if kind != 'cancelled':
        paired = len(record['table_ids']) == 2 or (before and len(before['table_ids']) == 2)
        table_field = 'table_ids' if paired else 'table_id'
        for key in (table_field, 'starts_at_local', 'party_size'):
            previous = before[key] if before else None
            value = record[key]
            if before is None or previous != value:
                changes.append({'field': key, 'from': copy.deepcopy(previous), 'to': copy.deepcopy(value)})
    return dict(seq=record['revision'], at=at or record['created_at'], event=kind, changes=changes,
                revision=record['revision'], accepted_terms=copy.deepcopy(record['accepted_terms']))


def initialize_records(state):
    """New fixtures and legacy migrations start with the information available.

    Earlier stages exported no history. Reconstruct a baseline from the current
    record, without inventing past amendments or cancellation timestamps.
    """
    state['policies'] = {rid: [] for rid in state['restaurants']}
    state['restaurant_revisions'] = {rid: 0 for rid in state['restaurants']}
    state['histories'] = {}
    state['series'] = {}
    for restaurant in state['restaurants'].values():
        restaurant.setdefault('manager_user_ids', [])
    for ref, record in state['reservations'].items():
        record['revision'] = 1
        record['accepted_terms'] = base_terms(state['restaurants'][record['restaurant_id']])
        state['histories'][ref] = [event(record)]
