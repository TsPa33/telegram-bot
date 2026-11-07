"""Plan-only annotations and reusable translations; never a second stock ledger."""

from sqlalchemy import (
    String,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db import Base
from app.models import uid, now


class DismantlingAnnotation(Base):
    __tablename__ = "dismantling_annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    vehicle_id: Mapped[str] = mapped_column(String(36))
    entry_key: Mapped[str] = mapped_column(String(100))
    name_uk: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    dismantled: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(
            ["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"]
        ),
        UniqueConstraint(
            "account_id", "vehicle_id", "entry_key", name="uq_dismantling_annotation"
        ),
    )


class PartNameTranslation(Base):
    __tablename__ = "part_name_translations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    source_key: Mapped[str] = mapped_column(String(240))
    original: Mapped[str] = mapped_column(String(240))
    translated: Mapped[str] = mapped_column(String(400))
    method: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("account_id", "source_key", name="uq_part_name_translation"),
    )
