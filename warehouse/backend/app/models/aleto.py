"""Tenant-local source catalogue. No relationship can mutate stock or finance."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, Numeric, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import uid


class AletoModel(Base):
    __tablename__ = 'aleto_models'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    manufacturer: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('account_id', 'manufacturer', 'model'), UniqueConstraint('id', 'account_id'))


class AletoOffer(Base):
    __tablename__ = 'aleto_offers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    source: Mapped[str] = mapped_column(String(20), default='aleto')
    source_article: Mapped[str] = mapped_column(String(150))
    title: Mapped[str] = mapped_column(Text)
    oem: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('account_id', 'source', 'source_article'), UniqueConstraint('id', 'account_id'), CheckConstraint("source = 'aleto'"))


class AletoPrice(Base):
    __tablename__ = 'aleto_prices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    offer_id: Mapped[str] = mapped_column(String(36), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    __table_args__ = (ForeignKeyConstraint(['offer_id', 'account_id'], ['aleto_offers.id', 'aleto_offers.account_id']), UniqueConstraint('offer_id', 'observed_at'), CheckConstraint('price_uah IS NULL OR price_uah >= 0'), CheckConstraint('price_usd IS NULL OR price_usd >= 0'))


class AletoApplication(Base):
    __tablename__ = 'aleto_applications'
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), primary_key=True)
    offer_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    __table_args__ = (ForeignKeyConstraint(['offer_id', 'account_id'], ['aleto_offers.id', 'aleto_offers.account_id']), ForeignKeyConstraint(['model_id', 'account_id'], ['aleto_models.id', 'aleto_models.account_id']))


class AletoTaxonomy(Base):
    __tablename__ = 'aleto_taxonomy'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    offer_id: Mapped[str] = mapped_column(String(36), index=True)
    model_id: Mapped[str] = mapped_column(String(36), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey('categories.id'))
    subcategory_id: Mapped[str | None] = mapped_column(ForeignKey('categories.id'), nullable=True)
    raw_category: Mapped[str] = mapped_column(String(200))
    raw_subcategory: Mapped[str] = mapped_column(String(200))
    normalization_status: Mapped[str] = mapped_column(String(20))
    __table_args__ = (ForeignKeyConstraint(['account_id', 'offer_id', 'model_id'], ['aleto_applications.account_id', 'aleto_applications.offer_id', 'aleto_applications.model_id']), UniqueConstraint('account_id', 'offer_id', 'model_id', 'raw_category', 'raw_subcategory'), CheckConstraint("(normalization_status = 'verified' AND subcategory_id IS NOT NULL) OR (normalization_status = 'pending' AND subcategory_id IS NULL)"))
