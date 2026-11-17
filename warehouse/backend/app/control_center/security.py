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
from .config import cipher, environment, get_db, password_only
from .models import Audit, Company, Grant, Session, Staff, Throttle, now, uid

COOKIE = "carpot_control_session"
COOKIE_PATH = "/api/control"
AUDIENCE = "carpot-control-center"
PASSWORD_AUDIENCE = "carpot-control-password-staging"


def session_audience():
    return PASSWORD_AUDIENCE if password_only() else AUDIENCE


hasher = PasswordHasher()
DUMMY = hasher.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session_csrf(token):
    """Domain-separated proof derived from the high-entropy HttpOnly session token."""
    return hmac.new(
        token.encode(), b"carpot-control-csrf-v1", hashlib.sha256
    ).hexdigest()


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


def throttle(db, username, ip, *, operation="login", commit=True):
    # Both account and IP budgets; persisted before password verification.
    for kind, value in [("user", username), ("ip", ip)]:
        key = digest(
            (operation + ":" if operation != "login" else "") + kind + ":" + value
        )
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
    if commit:
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
    simplified = password_only()
    step = None
    if valid and staff and staff.active and not simplified:
        try:
            step = mfa_step(
                cipher().decrypt(staff.mfa_ciphertext.encode()).decode(),
                code,
                staff.last_totp_step,
            )
        except (InvalidToken, ValueError):
            step = None
    if not (valid and staff and staff.active and (simplified or step is not None)):
        audit(
            db,
            staff.id if staff else "anonymous",
            "auth.login",
            "staff",
            "session",
            result="denied",
        )
        db.commit()
        raise HTTPException(401, "Перевірте облікові дані")
    if step is not None:
        staff.last_totp_step = step
    token = secrets.token_urlsafe(48)
    csrf = session_csrf(token)
    db.add(
        Session(
            token_hash=digest(token),
            staff_id=staff.id,
            csrf_hash=digest(csrf),
            audience=session_audience(),
            mfa_verified=not simplified,
            expires_at=now() + timedelta(hours=4),
        )
    )
    audit(
        db,
        staff.id,
        "auth.login",
        "staff",
        "session",
        diff={"auth_mode": "password-only" if simplified else "mfa"},
    )
    db.commit()
    return staff, token, csrf


def identity(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    session = db.get(Session, digest(token)) if token else None
    if (
        not session
        or session.audience != session_audience()
        or (not password_only() and not session.mfa_verified)
        or session.expires_at <= now()
    ):
        raise HTTPException(401, "Увійдіть у staff-акаунт")
    # Serialize staff commands with revoke/role changes, including in-flight writes.
    staff = db.scalar(
        select(Staff)
        .where(Staff.id == session.staff_id)
        .with_for_update(read=request.method in {"GET", "HEAD", "OPTIONS"})
    )
    if not staff or not staff.active:
        raise HTTPException(401, "Staff-доступ відкликано")
    expected_staff = request.headers.get("X-Control-Staff")
    if expected_staff and expected_staff != staff.id:
        raise HTTPException(401, "Staff-сесію змінено")
    session = db.scalar(
        select(Session)
        .where(Session.token_hash == digest(token))
        .execution_options(populate_existing=True)
    )
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Staff-сесію відкликано")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-Control-CSRF", "")
        # Recoverable cookie-bound proof also works with pre-upgrade sessions.
        # The old stored proof remains valid until that session expires/revokes.
        if (
            not csrf
            or len(csrf) > 128
            or not (
                hmac.compare_digest(digest(csrf), session.csrf_hash)
                or hmac.compare_digest(digest(csrf), digest(session_csrf(token)))
            )
        ):
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


def company(db, staff, company_id, *, write=False):
    row = db.scalar(
        select(Company)
        .where(
            Company.id == company_id,
            Company.environment == environment(),
            scope_query(staff),
        )
        .with_for_update(read=not write)
    )
    # A scope subquery can use a snapshot from before a row-lock wait. Recheck
    # the grant in a fresh READ COMMITTED statement after acquiring the lock.
    if row and not global_access(staff):
        grant = db.scalar(
            select(Grant.staff_id).where(
                Grant.company_id == row.id, Grant.staff_id == staff.id
            )
        )
        if grant is None:
            row = None
    if not row:
        raise HTTPException(404, "Компанію не знайдено")
    return row


def revoke(db, staff_id):
    db.execute(delete(Session).where(Session.staff_id == staff_id))


def require_step_up(db, staff, code, *, ip, password=None):
    """Policy-bound step-up for privilege changes in the same transaction."""
    throttle(db, staff.username, ip, operation="step-up", commit=False)
    if password_only():
        try:
            hasher.verify(staff.password_hash, password or "")
        except (VerificationError, InvalidHashError):
            audit(db, staff.id, "staff.step_up", "staff", staff.id, result="denied")
            db.commit()
            raise HTTPException(403, "Підтвердьте дію поточним паролем") from None
        return
    step = None
    try:
        if code:
            step = mfa_step(
                cipher().decrypt(staff.mfa_ciphertext.encode()).decode(),
                code,
                staff.last_totp_step,
            )
    except (InvalidToken, ValueError):
        pass
    if step is None:
        audit(db, staff.id, "staff.step_up", "staff", staff.id, result="denied")
        db.commit()
        raise HTTPException(403, "Для зміни доступу потрібен новий одноразовий MFA-код")
    staff.last_totp_step = step


def retire_staging_owner_mfa():
    """One-time retirement of preview keys and pending session-bound enrollment."""
    if not password_only():
        return 0
    from sqlalchemy.orm import Session as DBSession
    from .config import connection

    count = 0
    with DBSession(connection()) as db:
        owners = db.scalars(
            select(Staff)
            .where(Staff.role == "Owner")
            .order_by(Staff.id)
            .with_for_update()
        ).all()
        for staff in owners:
            retired = db.scalar(
                select(Audit.id)
                .where(
                    Audit.actor == staff.id,
                    Audit.permission == "auth.mfa_retired",
                    Audit.result == "success",
                )
                .limit(1)
            )
            if retired:
                continue
            # Never reuse or reveal a screenshot/enrollment seed. No new seed is enrolled.
            staff.mfa_ciphertext = (
                cipher().encrypt(base64.b32encode(secrets.token_bytes(20))).decode()
            )
            staff.last_totp_step = -1
            revoke(db, staff.id)
            audit(
                db,
                staff.id,
                "auth.mfa_retired",
                "staff",
                staff.id,
                reason="staging password-only policy; secure re-enrollment required before MFA use",
            )
            count += 1
        db.commit()
    return count
