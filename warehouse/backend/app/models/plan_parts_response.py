"""Durable provider request intents and bounded response receipts, tenant scoped."""

from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    JSON,
    LargeBinary,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid, now


class PlanPartsResponse(Base):
    __tablename__ = "plan_parts_responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    vehicle_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resource: Mapped[str] = mapped_column(String(30))
    parameters: Mapped[dict] = mapped_column(JSON)
    context_hash: Mapped[str] = mapped_column(String(64))
    request_key: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    body: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized: Mapped[list | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    estimated_max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"]
        ),
        UniqueConstraint("account_id", "request_key", name="uq_pp_response_request"),
        Index("ix_pp_response_context", "account_id", "context_hash", "created_at"),
        Index(
            "uq_pp_response_pending",
            "account_id",
            "context_hash",
            unique=True,
            postgresql_where=text("status IN ('pending','uncertain')"),
        ),
        CheckConstraint(
            "status IN ('pending','received','validated','invalid','uncertain','rejected')",
            name="ck_pp_response_status",
        ),
        CheckConstraint(
            "body IS NULL OR octet_length(body)<=2097152", name="ck_pp_response_size"
        ),
    )
