"""Workspace-scoped stable supplier type mapping; history is append-only JSON."""

from sqlalchemy import (
    String,
    Integer,
    JSON,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid


class SourceTypeMapping(Base):
    __tablename__ = "source_type_mappings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    source: Mapped[str] = mapped_column(String(40))
    pt_id: Mapped[int] = mapped_column(Integer)
    type_key: Mapped[str] = mapped_column(String(100))
    source_name: Mapped[str] = mapped_column(String(240))
    decision: Mapped[dict] = mapped_column(JSON)
    history: Mapped[list] = mapped_column(JSON)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    subcategory_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    __table_args__ = (UniqueConstraint("account_id", "source", "pt_id"),)
