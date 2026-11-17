from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Owner','Administrator','Manager','Support','Moderator')"
        ),
        {"schema": "control_center"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    mfa_ciphertext: Mapped[str] = mapped_column(Text)
    last_totp_step: Mapped[int] = mapped_column(Integer, default=-1)
    role: Mapped[str] = mapped_column(String(20))
    finance: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    temporary_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = ({"schema": "control_center"},)
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.staff.id"), index=True
    )
    csrf_hash: Mapped[str] = mapped_column(String(64))
    audience: Mapped[str] = mapped_column(String(40), default="carpot-control-center")
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Throttle(Base):
    __tablename__ = "login_buckets"
    __table_args__ = ({"schema": "control_center"},)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("environment", "workspace_id"),
        Index("cc_directory_order", "environment", "display_name", "id"),
        {"schema": "control_center"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    environment: Mapped[str] = mapped_column(String(20))
    workspace_id: Mapped[str] = mapped_column(String(36))
    display_name: Mapped[str] = mapped_column(String(120))
    # Search data is protected by the same server-side scope as detail.
    search_text: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[str | None] = mapped_column(
        ForeignKey("control_center.staff.id"), nullable=True, index=True
    )
    labels: Mapped[list] = mapped_column(JSON, default=list)
    snapshot: Mapped[dict] = mapped_column(JSON)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceLink(Base):
    __tablename__ = "source_links"
    __table_args__ = (
        UniqueConstraint("system", "environment", "entity_type", "source_id"),
        CheckConstraint("status IN ('proposed','verified','conflict','revoked')"),
        {"schema": "control_center"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.companies.id"), index=True
    )
    system: Mapped[str] = mapped_column(String(40))
    environment: Mapped[str] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(160))
    evidence: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    verified_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Grant(Base):
    __tablename__ = "company_grants"
    __table_args__ = ({"schema": "control_center"},)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.companies.id"), primary_key=True
    )
    staff_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.staff.id"), primary_key=True
    )


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = ({"schema": "control_center"},)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.companies.id"), index=True
    )
    staff_id: Mapped[str] = mapped_column(ForeignKey("control_center.staff.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','done')"),
        {"schema": "control_center"},
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.companies.id"), index=True
    )
    assignee_id: Mapped[str] = mapped_column(
        ForeignKey("control_center.staff.id"), index=True
    )
    next_action: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open")
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SourceState(Base):
    __tablename__ = "source_state"
    __table_args__ = ({"schema": "control_center"},)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    environment: Mapped[str] = mapped_column(String(20))
    schema_version: Mapped[str] = mapped_column(String(40))
    watermark: Mapped[str | None] = mapped_column(String(160), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    coverage: Mapped[str] = mapped_column(String(30), default="incomplete")


class Audit(Base):
    __tablename__ = "audit"
    __table_args__ = ({"schema": "control_center"},)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(80))
    permission: Mapped[str] = mapped_column(String(50))
    scope: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(80))
    request_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    safe_diff: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(String(30), default="success")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
