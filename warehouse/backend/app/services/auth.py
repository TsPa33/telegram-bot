import hashlib
import secrets
import time
from collections import OrderedDict
from datetime import timedelta
from threading import Lock
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Account, Session, now

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
_attempts = OrderedDict()
_lock = Lock()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(key):
    with _lock:
        stamp = time.monotonic()
        count, first = _attempts.get(key, (0, stamp))
        if stamp - first > 900:
            count, first = 0, stamp
        if count >= 20:
            raise HTTPException(429, "Забагато спроб. Спробуйте через 15 хвилин")
        _attempts[key] = (count + 1, first)
        _attempts.move_to_end(key)
        if len(_attempts) > 10000:
            _attempts.popitem(last=False)


def authenticate(db, email, password):
    user = db.scalar(select(Account).where(Account.email == email))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        raise HTTPException(401, "Невірна пошта або пароль")
    if not user:
        raise HTTPException(401, "Невірна пошта або пароль")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(password)
    return user


def create_session(db, user):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session = Session(
        token_hash=digest(token),
        account_id=user.id,
        csrf_hash=digest(csrf),
        expires_at=now() + timedelta(days=7),
    )
    db.add(session)
    return token, csrf
