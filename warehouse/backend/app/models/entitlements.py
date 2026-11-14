"""Product projections only. No payment ledger or financial authority in Warehouse."""

from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class EntitlementWorkspace(Base):
    __tablename__ = "warehouse_entitlement_workspaces"
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id"), primary_key=True
    )
    billing_account_id: Mapped[str] = mapped_column(String(80), unique=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"))
    mode: Mapped[str] = mapped_column(String(20), default="compatibility")
    version: Mapped[int] = mapped_column(Integer, default=0)
    intervals: Mapped[list] = mapped_column(JSON, default=list)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)


class EntitlementReceipt(Base):
    __tablename__ = "warehouse_entitlement_receipts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"))
    digest: Mapped[str] = mapped_column(String(64))


class DonorProvenance(Base):
    __tablename__ = "warehouse_donor_provenance"
    part_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parts.id"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"))
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["part_id", "workspace_id"], ["parts.id", "parts.account_id"]
        ),
        ForeignKeyConstraint(
            ["vehicle_id", "workspace_id"], ["vehicles.id", "vehicles.account_id"]
        ),
    )


class EntitlementReturn(Base):
    __tablename__ = "warehouse_entitlement_returns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"))
    sale_id: Mapped[str] = mapped_column(String(36), ForeignKey("operations.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("workspace_id", "request_key"),)
