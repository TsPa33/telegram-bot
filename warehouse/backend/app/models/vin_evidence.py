"""Audit-safe provider VIN evidence snapshots.

Staging first: shared provider evidence can be read only by platform admins.
A later release must enforce provider licensing and workspace rights before
allowing results to be reused by different customer workspaces.
"""
from datetime import datetime,timezone
from sqlalchemy import Boolean,DateTime,Integer,JSON,String,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import uid

class VinEvidenceSnapshot(Base):
    __tablename__ = "vin_evidence_snapshots"
    __table_args__ = (UniqueConstraint("provider","vin","contract_version",name="uq_vin_evidence_provider_vin_version"),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    provider: Mapped[str] = mapped_column(String(40),nullable=False)
    vin: Mapped[str] = mapped_column(String(17),nullable=False,index=True)
    contract_version: Mapped[str] = mapped_column(String(20),nullable=False)
    source: Mapped[str] = mapped_column(String(50),nullable=False)
    status: Mapped[str] = mapped_column(String(28),nullable=False)
    vehicle: Mapped[dict] = mapped_column(JSON,nullable=False)
    missing: Mapped[list] = mapped_column(JSON,nullable=False)
    logo_field_available: Mapped[bool] = mapped_column(Boolean,nullable=False,default=False)
    balance_before: Mapped[int|None] = mapped_column(Integer,nullable=True)
    balance_after: Mapped[int|None] = mapped_column(Integer,nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
