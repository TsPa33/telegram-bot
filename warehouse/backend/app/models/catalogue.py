"""Global reference catalogue; no stock/finance ownership or cascade to v1."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, JSON, Integer, DateTime, Numeric, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid, now


class CatalogueEntity(Base):
    __tablename__ = 'catalogue_entities'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(1000))
    normalized_name: Mapped[str] = mapped_column(String(1000))
    identity_key: Mapped[str] = mapped_column(String(64), unique=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint('id', 'kind', name='uq_catalogue_entity_kind'),
        ForeignKeyConstraint(['parent_id', 'parent_kind'], ['catalogue_entities.id', 'catalogue_entities.kind'], name='fk_catalogue_entity_parent'),
        CheckConstraint("(kind IN ('manufacturer','category') AND parent_id IS NULL AND parent_kind IS NULL) OR (parent_id IS NOT NULL AND ((kind='model' AND parent_kind='manufacturer') OR (kind='subcategory' AND parent_kind='category') OR (kind='part_type' AND parent_kind='subcategory')))", name='ck_catalogue_hierarchy'),
    )


class CatalogueAlias(Base):
    __tablename__ = 'catalogue_aliases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(20))
    context_id: Mapped[str] = mapped_column(String(36))
    alias_key: Mapped[str] = mapped_column(String(64))
    source_name: Mapped[str] = mapped_column(String(1000))
    target_id: Mapped[str] = mapped_column(String(36))
    verified_by: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    __table_args__ = (UniqueConstraint('kind','context_id','alias_key',name='uq_catalogue_alias'),
                      ForeignKeyConstraint(['target_id','kind'],['catalogue_entities.id','catalogue_entities.kind'],name='fk_catalogue_alias_kind'))


class CatalogueSource(Base):
    __tablename__ = 'catalogue_sources'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class CatalogueOffer(Base):
    __tablename__ = 'catalogue_offers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('catalogue_sources.id'), index=True)
    source_article: Mapped[str] = mapped_column(String(150))
    properties: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('source_id','source_article',name='uq_catalogue_source_article'),)


class CataloguePrice(Base):
    __tablename__ = 'catalogue_prices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey('catalogue_offers.id'), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_uah: Mapped[Decimal | None] = mapped_column(Numeric(14,2),nullable=True)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(14,2),nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint('offer_id','observed_at',name='uq_catalogue_observation'),
                      CheckConstraint('price_uah IS NULL OR price_uah >= 0',name='ck_catalogue_uah'),
                      CheckConstraint('price_usd IS NULL OR price_usd >= 0',name='ck_catalogue_usd'))


class CatalogueApplication(Base):
    __tablename__ = 'catalogue_applications'
    offer_id: Mapped[str] = mapped_column(ForeignKey('catalogue_offers.id'),primary_key=True)
    model_id: Mapped[str] = mapped_column(String(36),primary_key=True,index=True)
    model_kind: Mapped[str] = mapped_column(String(20),default='model')
    __table_args__ = (ForeignKeyConstraint(['model_id','model_kind'],['catalogue_entities.id','catalogue_entities.kind'],name='fk_catalogue_application_model'),CheckConstraint("model_kind='model'",name='ck_catalogue_model_kind'))


class CataloguePath(Base):
    __tablename__ = 'catalogue_paths'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    offer_id: Mapped[str] = mapped_column(String(36),index=True)
    model_id: Mapped[str] = mapped_column(String(36),index=True)
    part_type_id: Mapped[str | None] = mapped_column(String(36),nullable=True,index=True)
    part_kind: Mapped[str | None] = mapped_column(String(20),nullable=True)
    path_key: Mapped[str] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('offer_id','model_id','path_key',name='uq_catalogue_path'),
                      ForeignKeyConstraint(['offer_id','model_id'],['catalogue_applications.offer_id','catalogue_applications.model_id'],name='fk_catalogue_path_application'),
                      ForeignKeyConstraint(['part_type_id','part_kind'],['catalogue_entities.id','catalogue_entities.kind'],name='fk_catalogue_path_type'),
                      CheckConstraint("(part_type_id IS NULL AND part_kind IS NULL) OR (part_type_id IS NOT NULL AND part_kind='part_type')",name='ck_catalogue_path_type'))


class CatalogueState(Base):
    __tablename__ = 'catalogue_state'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint('id=1 AND revision>=0',name='ck_catalogue_state'),)


class CatalogueJob(Base):
    __tablename__ = 'catalogue_jobs'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'),index=True)
    filename: Mapped[str] = mapped_column(String(200))
    file_sha256: Mapped[str] = mapped_column(String(64),index=True)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    rows: Mapped[list] = mapped_column(JSON)
    format: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20),default='uploaded')
    resolutions: Mapped[dict] = mapped_column(JSON,default=dict)
    report: Mapped[dict] = mapped_column(JSON,default=dict)
    preview_token: Mapped[str | None] = mapped_column(String(64),nullable=True)
    catalogue_revision: Mapped[int | None] = mapped_column(Integer,nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__ = (CheckConstraint("status IN ('uploaded','review','ready','applied','failed')",name='ck_catalogue_job_status'),)
