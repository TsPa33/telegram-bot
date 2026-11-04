"""Workspace-scoped evidence of paid provider responses, never a supplier offer catalogue."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid, now


class PlanPartsArticleReceipt(Base):
    __tablename__ = "plan_parts_article_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_pp_receipt_donor_account"),
        UniqueConstraint("account_id", "vehicle_id", "ktype", "pt_id", name="uq_pp_article_receipt_scope"),
        CheckConstraint("ktype > 0 AND pt_id > 0 AND article_count >= 0", name="ck_pp_article_receipt_values"),
        CheckConstraint("status IN ('received','unavailable','uncertain')", name="ck_pp_article_receipt_status"),
        Index("ix_pp_article_receipts_vehicle_scope", "account_id", "vehicle_id", "ktype"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ktype: Mapped[int] = mapped_column(Integer, nullable=False)
    pt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    article_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
