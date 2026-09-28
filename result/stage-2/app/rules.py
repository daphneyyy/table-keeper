"""Strict JSON validation and shared restaurant time/occupancy rules."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .json_values import Number, number_equal

UTC = timezone.utc
WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


class Error(Exception):
    def __init__(self, status=422, code='validation_failed', message=None):
        self.status, self.code, self.message = status, code, message or code.replace('_', ' ')


def require(condition, status=422, code='validation_failed'):
    if not condition:
        raise Error(status, code)


def field(obj, key, kind=str):
    require(key in obj)
    value = obj[key]
    require(type(value) is kind, 400, 'malformed_request')
    return value


def identifier(obj, key):
    value = field(obj, key)
    require(0 < len(value) <= 64)
    return value


def positive(obj, key, minimum=1):
    value = field(obj, key, int)
    require(value >= minimum)
    return value


def party(value):
    require(type(value) is int and value >= 1)
    return value


def date_text(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value))
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise Error() from None


def local_text(value):
    require(type(value) is str, 400, 'malformed_request')
    require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}', value))
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M')
    except ValueError:
        raise Error() from None


def clock(value):
    require(type(value) is str, 400, 'malformed_request')
    require(re.fullmatch(r'[0-9]{2}:[0-9]{2}', value))
    h, m = map(int, value.split(':'))
    require(h < 24 and m < 60)
    return h * 60 + m


def resolve(zone, naive):
    aware = naive.replace(tzinfo=ZoneInfo(zone), fold=0)
    require(aware.astimezone(UTC).astimezone(aware.tzinfo).replace(tzinfo=None) == naive,
            422, 'invalid_local_time')
    return aware


def instant(value):
    require(type(value) is str)
    try:
        parsed = datetime.fromisoformat(value)
        require(parsed.tzinfo is not None)
        return parsed.astimezone(UTC)
    except ValueError:
        raise Error() from None


def timestamp(value):
    # Historical IANA local-mean-time offsets can include seconds, which RFC3339
    # does not permit. UTC preserves the exact instant without rounding offsets.
    if value.utcoffset().total_seconds() % 60:
        value = value.astimezone(UTC)
    return value.isoformat()


def hours(restaurant, day):
    return next((x for x in restaurant['opening_hours'] if x['weekday'] == WEEKDAYS[day.weekday()]), None)


def booking(restaurant, fields):
    table_id = identifier(fields, 'table_id')
    table = next((x for x in restaurant['tables'] if x['id'] == table_id), None)
    require(table is not None, 404, 'not_found')
    require('party_size' in fields and 'starts_at_local' in fields)
    size = party(fields['party_size'])
    naive = local_text(fields['starts_at_local'])
    start = resolve(restaurant['timezone'], naive)
    require(size <= table['capacity'], 422, 'party_exceeds_capacity')
    opening = hours(restaurant, naive)
    require(opening is not None, 422, 'outside_opening_hours')
    minute = naive.hour * 60 + naive.minute
    opens, closes = clock(opening['opens']), clock(opening['closes'])
    require(opens <= minute < closes, 422, 'outside_opening_hours')
    require((minute - opens) % restaurant['slot_minutes'] == 0, 422, 'not_on_slot_grid')
    try:
        end = start.astimezone(UTC) + timedelta(minutes=restaurant['reservation_duration_minutes'])
        closing = resolve(restaurant['timezone'], naive.replace(hour=closes // 60, minute=closes % 60))
        require(end <= closing.astimezone(UTC), 422, 'outside_opening_hours')
        end = end.astimezone(start.tzinfo)
    except (OverflowError, ValueError):
        raise Error(422, 'outside_opening_hours') from None
    return dict(restaurant_id=restaurant['id'], table_id=table_id, party_size=size,
                starts_at_local=fields['starts_at_local'], starts_at=timestamp(start), ends_at=timestamp(end))


def overlaps(a, b):
    return (a['restaurant_id'] == b['restaurant_id'] and a['table_id'] == b['table_id']
            and instant(a['starts_at']) < instant(b['ends_at'])
            and instant(b['starts_at']) < instant(a['ends_at']))


def check_occupancy(candidates, existing):
    occupied = [r for r in existing if r['status'] == 'confirmed']
    for candidate in candidates:
        if candidate['status'] == 'confirmed':
            require(not any(overlaps(candidate, r) for r in occupied), 409, 'table_unavailable')
            occupied.append(candidate)


def json_equal(a, b):
    # JSON numbers compare numerically, but booleans are a distinct JSON type.
    if type(a) in (int, Number) and type(b) in (int, Number):
        return number_equal(a, b)
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return a == b
