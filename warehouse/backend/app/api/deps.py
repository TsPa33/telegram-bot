import hmac
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from app.db import get_db
from app.models import Account, Session, now
from app.services.auth import digest


@dataclass
class Identity:
    user: Account
    session: Session


def identity(request: Request, db: DBSession = Depends(get_db)):
    token = request.cookies.get("warehouse_session", "")
    session = db.get(Session, digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Увійдіть до облікового запису")
    user = db.get(Account, session.account_id)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(digest(csrf), session.csrf_hash):
            raise HTTPException(403, "Недійсний CSRF-токен. Оновіть сторінку")
    return Identity(user, session)
