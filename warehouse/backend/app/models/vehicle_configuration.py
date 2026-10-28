"""Append-only workspace engineering facts; never updates a vehicle or donor plan."""
from datetime import datetime
from sqlalchemy import String,JSON,DateTime,ForeignKey,ForeignKeyConstraint,CheckConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import now
class VehicleConfiguration(Base):
    __tablename__='vehicle_configurations'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    account_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'),index=True)
    vehicle_id:Mapped[str]=mapped_column(String(36),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    status:Mapped[str]=mapped_column(String(10))
    preview_id:Mapped[str|None]=mapped_column(ForeignKey('vehicle_configurations.id'),nullable=True)
    basis_sha:Mapped[str]=mapped_column(String(64))
    token:Mapped[str]=mapped_column(String(64))
    facts:Mapped[list]=mapped_column(JSON)
    report:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(ForeignKeyConstraint(['vehicle_id','account_id'],['vehicles.id','vehicles.account_id']),CheckConstraint("status IN ('preview','confirmed')",name='ck_vehicle_configuration_status'),)
