"""Isolated Warehouse billing ledger; never links Telegram sellers."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String,Integer,Boolean,DateTime,ForeignKey,Numeric,UniqueConstraint,CheckConstraint,ForeignKeyConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import uid,now

class WorkspaceSubscription(Base):
    __tablename__='warehouse_subscriptions'
    workspace_id:Mapped[str]=mapped_column(String(36),ForeignKey('accounts.id'),primary_key=True)
    plan:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(20),default='inactive')
    period_start:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    period_end:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    grace_end:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    auto_renew:Mapped[bool]=mapped_column(Boolean,default=False)
    provider_id:Mapped[str|None]=mapped_column(String(160))

class BillingPayment(Base):
    __tablename__='warehouse_billing_payments'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    workspace_id:Mapped[str]=mapped_column(String(36),ForeignKey('accounts.id'),index=True)
    request_key:Mapped[str]=mapped_column(String(80))
    product:Mapped[str]=mapped_column(String(30))
    amount:Mapped[Decimal]=mapped_column(Numeric(12,2))
    currency:Mapped[str]=mapped_column(String(3),default='UAH')
    status:Mapped[str]=mapped_column(String(24),default='pending')
    provider_id:Mapped[str|None]=mapped_column(String(160))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    confirmed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('workspace_id','request_key'),UniqueConstraint('id','workspace_id'),CheckConstraint('amount>0'))

class DismantlingCredit(Base):
    __tablename__='warehouse_dismantling_credits'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    workspace_id:Mapped[str]=mapped_column(String(36),ForeignKey('accounts.id'),index=True)
    payment_id:Mapped[str]=mapped_column(String(36),ForeignKey('warehouse_billing_payments.id'),unique=True)
    source:Mapped[str]=mapped_column(String(20))
    granted:Mapped[int]=mapped_column(Integer)
    used:Mapped[int]=mapped_column(Integer,default=0)
    expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint('granted>0 AND used>=0 AND used<=granted'),UniqueConstraint('id','workspace_id'),ForeignKeyConstraint(['payment_id','workspace_id'],['warehouse_billing_payments.id','warehouse_billing_payments.workspace_id']))

class DismantlingUsage(Base):
    __tablename__='warehouse_dismantling_usage'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    workspace_id:Mapped[str]=mapped_column(String(36),ForeignKey('accounts.id'),index=True)
    vehicle_id:Mapped[str]=mapped_column(String(36),ForeignKey('vehicles.id'))
    ktype:Mapped[int]=mapped_column(Integer)
    operation_key:Mapped[str]=mapped_column(String(80))
    status:Mapped[str]=mapped_column(String(20),default='reserved')
    credit_id:Mapped[str|None]=mapped_column(String(36),ForeignKey('warehouse_dismantling_credits.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(ForeignKeyConstraint(['vehicle_id','workspace_id'],['vehicles.id','vehicles.account_id']),ForeignKeyConstraint(['credit_id','workspace_id'],['warehouse_dismantling_credits.id','warehouse_dismantling_credits.workspace_id']),UniqueConstraint('workspace_id','vehicle_id','ktype'),UniqueConstraint('workspace_id','operation_key'))

class BillingEvent(Base):
    __tablename__='warehouse_billing_events'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    workspace_id:Mapped[str]=mapped_column(String(36),ForeignKey('accounts.id'),index=True)
    payment_id:Mapped[str]=mapped_column(String(36),ForeignKey('warehouse_billing_payments.id'))
    kind:Mapped[str]=mapped_column(String(40))
    status:Mapped[str]=mapped_column(String(24))
    received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

BillingEvent.__table__.append_constraint(ForeignKeyConstraint(['payment_id','workspace_id'],['warehouse_billing_payments.id','warehouse_billing_payments.workspace_id']))
