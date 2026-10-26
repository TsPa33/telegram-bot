"""Orders own commercial snapshots; Part and Operation remain the stock ledger."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid, now


class Buyer(Base):
    __tablename__ = 'buyers'
    __table_args__ = (UniqueConstraint('id', 'account_id', name='uq_buyer_id_account'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    phone_normalized: Mapped[str] = mapped_column(String(20), index=True)
    additional_phone: Mapped[str] = mapped_column(String(50), default='')
    additional_phone_normalized: Mapped[str] = mapped_column(String(20), default='', index=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        UniqueConstraint('id', 'account_id', name='uq_order_id_account'),
        UniqueConstraint('account_id', 'number', name='uq_order_account_number'),
        ForeignKeyConstraint(['buyer_id', 'account_id'], ['buyers.id', 'buyers.account_id'], name='fk_order_buyer_account'),
        CheckConstraint('number > 0', name='ck_order_number'),
        CheckConstraint("status IN ('new','reserved','shipped','completed','cancelled')", name='ck_order_status'),
        CheckConstraint("delivery_method IN ('pickup','branch','address')", name='ck_order_delivery'),
        CheckConstraint("delivery_method = 'pickup' OR (city <> '' AND delivery_address <> '')", name='ck_order_delivery_address'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    buyer_id: Mapped[str] = mapped_column(String(36))
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_phone: Mapped[str] = mapped_column(String(50))
    contact_phone_normalized: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default='new')
    delivery_method: Mapped[str] = mapped_column(String(20), default='pickup')
    city: Mapped[str] = mapped_column(String(150), default='')
    delivery_address: Mapped[str] = mapped_column(String(300), default='')
    tracking_number: Mapped[str] = mapped_column(String(100), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrderLine(Base):
    __tablename__ = 'order_lines'
    __table_args__ = (
        UniqueConstraint('id','account_id','part_id', name='uq_order_line_identity'),
        ForeignKeyConstraint(['order_id','account_id'], ['orders.id','orders.account_id'], name='fk_line_order_account'),
        ForeignKeyConstraint(['part_id','account_id'], ['parts.id','parts.account_id'], name='fk_line_part_account'),
        CheckConstraint('quantity > 0 AND quantity <= 1000000', name='ck_order_line_quantity'),
        CheckConstraint('unit_price >= 0', name='ck_order_line_price'),
        CheckConstraint("currency IN ('UAH','USD')", name='ck_order_line_currency'),
        CheckConstraint('line_total = quantity * unit_price', name='ck_order_line_total'),
        Index('uq_order_active_part','order_id','part_id',unique=True,postgresql_where=text('active')),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    order_id: Mapped[str] = mapped_column(String(36), index=True)
    part_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    donor_snapshot: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14,2))
    currency: Mapped[str] = mapped_column(String(3))
    line_total: Mapped[Decimal] = mapped_column(Numeric(20,2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sale_operation_id: Mapped[str | None] = mapped_column(ForeignKey('operations.id'),nullable=True,unique=True)


class OrderReservation(Base):
    __tablename__ = 'order_reservations'
    __table_args__ = (
        ForeignKeyConstraint(['order_line_id','account_id','part_id'], ['order_lines.id','order_lines.account_id','order_lines.part_id'], name='fk_reservation_line_account_part'),
        CheckConstraint('quantity > 0', name='ck_order_reservation_quantity'),
        CheckConstraint("state IN ('active','released','consumed')", name='ck_order_reservation_state'),
        Index('uq_order_active_reservation','order_line_id',unique=True,postgresql_where=text("state = 'active'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    order_line_id: Mapped[str] = mapped_column(String(36), index=True)
    part_id: Mapped[str] = mapped_column(String(36), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default='active')
    reserve_operation_id: Mapped[str] = mapped_column(ForeignKey('operations.id'), unique=True)
    release_operation_id: Mapped[str | None] = mapped_column(ForeignKey('operations.id'), nullable=True, unique=True)
    sale_operation_id: Mapped[str | None] = mapped_column(ForeignKey('operations.id'), nullable=True, unique=True)


class OrderEvent(Base):
    __tablename__ = 'order_events'
    __table_args__ = (ForeignKeyConstraint(['order_id','account_id'], ['orders.id','orders.account_id'], name='fk_event_order_account'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    order_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrderRequest(Base):
    __tablename__ = 'order_requests'
    __table_args__ = (UniqueConstraint('account_id','request_key',name='uq_order_request_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    request_key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
