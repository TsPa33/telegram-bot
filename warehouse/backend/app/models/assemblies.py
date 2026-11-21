"""Physical memberships extend existing donor placements; no second stock ledger."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid, now


class AssemblyMembership(Base):
    __tablename__ = 'assembly_memberships'
    __table_args__ = (
        ForeignKeyConstraint(['parent_item_id','account_id','vehicle_id'],['dismantling_items.id','dismantling_items.account_id','dismantling_items.vehicle_id'],name='fk_assembly_parent_scope'),
        ForeignKeyConstraint(['child_item_id','account_id','vehicle_id'],['dismantling_items.id','dismantling_items.account_id','dismantling_items.vehicle_id'],name='fk_assembly_child_scope'),
        CheckConstraint('parent_item_id <> child_item_id',name='ck_assembly_not_self'),
        CheckConstraint('(active AND detached_at IS NULL AND detached_operation_id IS NULL) OR (NOT active AND detached_at IS NOT NULL AND detached_operation_id IS NOT NULL)',name='ck_assembly_detach_evidence'),
        Index('uq_assembly_active_child','child_item_id',unique=True,postgresql_where=text('active')),
    )
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'),index=True)
    vehicle_id: Mapped[str] = mapped_column(String(36),index=True)
    parent_item_id: Mapped[str] = mapped_column(String(36),index=True)
    child_item_id: Mapped[str] = mapped_column(String(36),index=True)
    active: Mapped[bool] = mapped_column(Boolean,default=True,server_default='true')
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    detached_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True),nullable=True)
    attached_operation_id: Mapped[str] = mapped_column(ForeignKey('operations.id'))
    detached_operation_id: Mapped[str|None] = mapped_column(ForeignKey('operations.id'),nullable=True)


class AssemblyTemplate(Base):
    __tablename__='assembly_templates'
    __table_args__=(UniqueConstraint('account_id','name','version',name='uq_assembly_template_version'),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'),index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
