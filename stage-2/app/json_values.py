"""JSON numbers without binary-float or Decimal exponent limits.

Non-integer tokens retain their original JSON spelling. Equality uses a normalized
sign/coefficient/exponent triple, never expansion of exponent-sized zero strings.
The parser supplies only syntactically validated JSON number tokens. RawJSON is
used exclusively for those tokens and integer strings generated here.
"""
from dataclasses import dataclass

import simplejson
from simplejson.raw_json import RawJSON


def integer(text):
    """Parse without Python's decimal-string digit cap or global settings."""
    negative = text.startswith('-')
    digits = text.lstrip('+-')
    value = 0
    for offset in range(0, len(digits), 9):
        chunk = digits[offset:offset + 9]
        value = value * (10 ** len(chunk)) + int(chunk)
    return -value if negative else value


def integer_text(value):
    if value.bit_length() < 14000:
        return str(value)
    negative = value < 0
    value = abs(value)
    chunks = []
    while value:
        value, remainder = divmod(value, 1_000_000_000)
        chunks.append(remainder)
    return ('-' if negative else '') + str(chunks[-1]) + ''.join(f'{x:09d}' for x in reversed(chunks[:-1]))


def normalized(token):
    mantissa, separator, exponent = token.lower().partition('e')
    negative = mantissa.startswith('-')
    whole, dot, fraction = mantissa.lstrip('-').partition('.')
    digits = (whole + fraction).lstrip('0')
    if not digits:
        return False, '0', 0
    trimmed = digits.rstrip('0')
    power = (integer(exponent) if separator else 0) - len(fraction) + len(digits) - len(trimmed)
    return negative, trimmed, power


@dataclass(frozen=True)
class Number:
    token: str

    def canonical(self):
        return normalized(self.token)


def number_equal(a, b):
    left = a.canonical() if isinstance(a, Number) else normalized(integer_text(a))
    right = b.canonical() if isinstance(b, Number) else normalized(integer_text(b))
    return left == right


def reject_constant(_):
    raise ValueError('not a JSON number')


def loads(raw):
    return simplejson.loads(raw, parse_float=Number, parse_int=integer, parse_constant=reject_constant)


def encodable(value):
    if isinstance(value, Number):
        return RawJSON(value.token)
    if type(value) is int and value.bit_length() >= 14000:
        return RawJSON(integer_text(value))
    if isinstance(value, dict):
        return {key: encodable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encodable(item) for item in value]
    return value


def dumps(value):
    return simplejson.dumps(encodable(value), ensure_ascii=True, allow_nan=False)
