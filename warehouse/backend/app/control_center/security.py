"""Separate staff credentials; RFC6238 MFA and durable rate limiting."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from cryptography.fernet import InvalidToken
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from .config import cipher, environment, get_db
from .models import Audit, Company, Grant, Session, Staff, Throttle, now, uid

COOKIE = "carpot_control_session"
COOKIE_PATH = "/api/control"
AUDIENCE = "carpot-control-center"
hasher = PasswordHasher()
DUMMY = hasher.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def totp(secret, step):
    key = base64.b32decode(secret, casefold=True)
    if not 20 <= len(key) <= 64:
        raise ValueError("MFA seed must contain 20–64 random bytes")
    raw = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = raw[-1] & 15
    return f"{(struct.unpack('>I', raw[off : off + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def mfa_step(secret, code, last=-1, stamp=None):
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    step = int(time.time() if stamp is None else stamp) // 30
    for candidate in (step, step - 1, step + 1):
        if candidate > last and hmac.compare_digest(totp(secret, candidate), code):
            return candidate
    return None


def audit(
    db, actor, permission, scope, target, *, diff=None, reason=None, result="success"
):
    db.add(
        Audit(
            actor=actor,
            permission=permission,
            scope=scope,
            target=target,
            request_id=uid(),
            reason=reason,
            safe_diff=diff or {},
            result=result,
        )
    )


def throttle(db, username, ip):
    # Both account and IP budgets; persisted before password verification.
    for kind, value in [("user", username), ("ip", ip)]:
        key = digest(kind + ":" + value)
        db.execute(
            insert(Throttle)
            .values(key=key, attempts=0, until=now() + timedelta(minutes=15))
            .on_conflict_do_nothing()
        )
        bucket = db.get(Throttle, key, with_for_update=True)
        if bucket.until <= now():
            bucket.attempts, bucket.until = 0, now() + timedelta(minutes=15)
        if bucket.attempts >= (12 if kind == "user" else 60):
            db.commit()
            raise HTTPException(429, "Забагато спроб. Спробуйте пізніше")
        bucket.attempts += 1
    db.commit()


def login(db, username, password, code, ip):
    username = username.strip().lower()
    throttle(db, username, ip)
    staff = db.scalar(select(Staff).where(Staff.username == username).with_for_update())
    valid = True
    try:
        hasher.verify(staff.password_hash if staff else DUMMY, password)
    except (VerificationError, InvalidHashError):
        valid = False
    step = None
    if valid and staff and staff.active:
        try:
            step = mfa_step(
                cipher().decrypt(staff.mfa_ciphertext.encode()).decode(),
                code,
                staff.last_totp_step,
            )
        except (InvalidToken, ValueError):
            step = None
    if step is None:
        audit(
            db,
            staff.id if staff else "anonymous",
            "auth.login",
            "staff",
            "session",
            result="denied",
        )
        db.commit()
        raise HTTPException(401, "Перевірте логін, пароль і MFA-код")
    staff.last_totp_step = step
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        Session(
            token_hash=digest(token),
            staff_id=staff.id,
            csrf_hash=digest(csrf),
            audience=AUDIENCE,
            mfa_verified=True,
            expires_at=now() + timedelta(hours=4),
        )
    )
    audit(db, staff.id, "auth.login", "staff", "session")
    db.commit()
    return staff, token, csrf


def identity(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    session = db.get(Session, digest(token)) if token else None
    if (
        not session
        or session.audience != AUDIENCE
        or not session.mfa_verified
        or session.expires_at <= now()
    ):
        raise HTTPException(401, "Увійдіть із staff MFA")
    # Serialize staff commands with revoke/role changes, including in-flight writes.
    staff = db.scalar(
        select(Staff).where(Staff.id == session.staff_id).with_for_update(read=True)
    )
    if not staff or not staff.active:
        raise HTTPException(401, "Staff-доступ відкликано")
    session = db.scalar(
        select(Session)
        .where(Session.token_hash == digest(token))
        .execution_options(populate_existing=True)
    )
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Staff-сесію відкликано")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-Control-CSRF", "")
        if not csrf or not hmac.compare_digest(digest(csrf), session.csrf_hash):
            raise HTTPException(403, "Недійсний CSRF-токен")
    request.state.control_session = session
    return staff


def global_access(staff):
    return staff.role in {"Owner", "Administrator"}


def finance_access(staff):
    return staff.role == "Owner" or (staff.role != "Support" and staff.finance)


def scope_query(staff):
    if global_access(staff):
        return True
    return Company.id.in_(select(Grant.company_id).where(Grant.staff_id == staff.id))


def company(db, staff, company_id):
    row = db.scalar(
        select(Company).where(
            Company.id == company_id,
            Company.environment == environment(),
            scope_query(staff),
        )
    )
    if not row:
        raise HTTPException(404, "Компанію не знайдено")
    return row


def revoke(db, staff_id):
    db.execute(delete(Session).where(Session.staff_id == staff_id))
