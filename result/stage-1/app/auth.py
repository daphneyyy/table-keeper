"""Salted scrypt credentials. No plaintext passwords are retained in state."""
import hashlib
import hmac
import re
import secrets
from threading import BoundedSemaphore

from .rules import field, require

HASH_SLOTS = BoundedSemaphore(4)


def credentials(body, signup=False):
    email, password = field(body, 'email'), field(body, 'password')
    if signup:
        require(re.fullmatch(r'[^\s@]+@[^\s@]+', email) is not None)
        require(len(password) >= 8)
        field(body, 'display_name')
    return email, password


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    with HASH_SLOTS:
        digest = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                                n=16384, r=8, p=1, dklen=32).hex()
    return {'algorithm': 'scrypt', 'n': 16384, 'r': 8, 'p': 1, 'salt': salt, 'digest': digest}


def validate_hash(value):
    require(type(value) is dict and set(value) == {'algorithm', 'n', 'r', 'p', 'salt', 'digest'})
    require(value['algorithm'] == 'scrypt' and type(value['n']) is int and value['n'] == 16384
            and type(value['r']) is int and value['r'] == 8 and type(value['p']) is int and value['p'] == 1)
    require(type(value['salt']) is str and re.fullmatch('[a-f0-9]{32}', value['salt']) is not None)
    require(type(value['digest']) is str and re.fullmatch('[a-f0-9]{64}', value['digest']) is not None)


def verify(password, stored):
    return hmac.compare_digest(hash_password(password, stored['salt'])['digest'], stored['digest'])
