"""Durable reviewed pricing commands, never a stock or market-price ledger."""
from datetime import datetime
from sqlalchemy import String,JSON,DateTime,ForeignKey,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import uid,now
class PriceDecision(Base):
    __tablename__='price_decisions'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    request_key:Mapped[str]=mapped_column(String(36))
    fingerprint:Mapped[str]=mapped_column(String(64))
    token:Mapped[str]=mapped_column(String(64))
    command:Mapped[dict]=mapped_column(JSON)
    report:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(10),default='preview')
    apply_key:Mapped[str|None]=mapped_column(String(36),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('account_id','request_key'),UniqueConstraint('account_id','apply_key'),CheckConstraint("status IN ('preview','applied')",name='ck_price_decision_status'))
