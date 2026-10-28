"""Command replay protection only; Part/Operation remain the sole stock ledger."""
from sqlalchemy import String,JSON,DateTime,ForeignKey,ForeignKeyConstraint,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from datetime import datetime
from app.db import Base
from app.models import uid,now
class DismantlingRequest(Base):
    __tablename__='dismantling_requests'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    vehicle_id:Mapped[str]=mapped_column(String(36))
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    request_key:Mapped[str]=mapped_column(String(36))
    request_sha:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(ForeignKeyConstraint(['vehicle_id','account_id'],['vehicles.id','vehicles.account_id']),UniqueConstraint('account_id','request_key',name='uq_dismantling_request_key'))
