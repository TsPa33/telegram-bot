from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import (
    true,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    workspace_account_id: Mapped[str | None] = mapped_column(ForeignKey('accounts.id'), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default='DIRECTOR', server_default='DIRECTOR')
    permissions: Mapped[list] = mapped_column(JSON, default=list, server_default='[]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("(role='DIRECTOR' AND workspace_account_id IS NULL) OR (role IN ('ADMIN','MANAGER') AND workspace_account_id IS NOT NULL AND workspace_account_id<>id)", name='ck_account_workspace_role'),)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Owned:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Vehicle(Owned, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("account_id", "donor_id"),
        UniqueConstraint("account_id", "number", name="uq_vehicle_account_number"),
        CheckConstraint("number > 0", name="ck_vehicle_number_positive"),
        UniqueConstraint("id", "account_id", name="uq_vehicles_id_account"),
        CheckConstraint("year BETWEEN 1886 AND 2100"),
        CheckConstraint("acquisition_cost IS NULL OR acquisition_cost >= 0"),
        CheckConstraint("ktype IS NULL OR ktype > 0", name="ck_vehicle_ktype_positive"),
    )
    manufacturer: Mapped[str] = mapped_column(String(100))
    ktype: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checklist_ktype: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checklist_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model: Mapped[str] = mapped_column(String(100))
    generation: Mapped[str] = mapped_column(String(100), default="")
    year: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(100), default="")
    fuel_type: Mapped[str] = mapped_column(String(50), default="")
    transmission: Mapped[str] = mapped_column(String(50), default="")
    vin: Mapped[str | None] = mapped_column(String(17), nullable=True)
    donor_id: Mapped[str] = mapped_column(String(80))
    number: Mapped[int] = mapped_column(Integer)
    acquisition_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="dismantling")


class Category(Owned, Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("account_id", "source", "external_key"),
        CheckConstraint("kind IN ('category','subcategory','part')"),
    )
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(100))
    external_key: Mapped[str] = mapped_column(String(200))


class VehicleChecklistItem(Base):
    """Potential type for one donor, never an inventory/quantity record."""
    __tablename__ = "vehicle_checklist_items"
    __table_args__ = (
        ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_checklist_vehicle_account"),
        UniqueConstraint("vehicle_id", "source", "ktype", "pt_id", name="uq_checklist_vehicle_type"),
        CheckConstraint("ktype > 0 AND pt_id > 0 AND article_count >= 0", name="ck_checklist_provider_values"),
        CheckConstraint("status IN ('unchecked','present','absent','damaged')", name="ck_checklist_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(100), default="plan.parts")
    ktype: Mapped[int] = mapped_column(Integer)
    pt_id: Mapped[int] = mapped_column(Integer)
    name_en: Mapped[str] = mapped_column(String(200))
    name_uk: Mapped[str] = mapped_column(String(200), default="")
    article_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="unchecked")
    notes: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Part(Owned, Base):
    __tablename__ = "parts"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_part_id_account"),
        UniqueConstraint("vehicle_id", "checklist_category_id"),
        UniqueConstraint("account_id", "serial_number"),
        CheckConstraint(
            "quantity >= 0 AND reserved_quantity >= 0 AND reserved_quantity <= quantity"
        ),
        CheckConstraint("NOT individually_tracked OR quantity <= 1"),
        CheckConstraint("selling_price IS NULL OR selling_price >= 0"),
        CheckConstraint("currency IN ('UAH','USD')", name="ck_part_currency"),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0"),
        CheckConstraint("availability IN ('unchecked','present','absent','damaged')"),
        CheckConstraint("condition IN ('used','new','damaged','refurbished')"),
    )
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    subcategory_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("vehicles.id"), nullable=True, index=True
    )
    checklist_category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    oem_number: Mapped[str] = mapped_column(String(150), default="")
    article_number: Mapped[str] = mapped_column(String(150), default="")
    condition: Mapped[str] = mapped_column(String(30), default="used")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="UAH", server_default="UAH")
    location: Mapped[str] = mapped_column(String(120), default="")
    compatibility_notes: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    availability: Mapped[str] = mapped_column(String(30), default="unchecked")
    individually_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)

    @property
    def available_quantity(self):
        return self.quantity - self.reserved_quantity


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    part_id: Mapped[str | None] = mapped_column(
        ForeignKey("parts.id"), nullable=True, index=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(
        ForeignKey("vehicles.id"), nullable=True
    )
    entity_id: Mapped[str] = mapped_column(String(36))
    entity_type: Mapped[str] = mapped_column(String(30))
    type: Mapped[str] = mapped_column(String(50), index=True)
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.id"), index=True)
    filename: Mapped[str] = mapped_column(String(80))
    media_type: Mapped[str] = mapped_column(String(30))


class DismantlingItem(Base):
    """Local workflow state; actual stock is exclusively Part + Operation."""
    __tablename__ = "dismantling_items"
    __table_args__ = (
        ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_dismantling_vehicle_account"),
        UniqueConstraint("vehicle_id", "source", "catalog_key", name="uq_dismantling_catalog_key"),
        UniqueConstraint("part_id", name="uq_dismantling_part"),
        CheckConstraint("status IN ('unchecked','dismantled','absent','damaged')", name="ck_dismantling_status"),
        CheckConstraint("quantity > 0 AND quantity <= 1000000", name="ck_dismantling_quantity"),
        CheckConstraint("condition IS NULL OR condition IN ('used','new','damaged','refurbished')", name="ck_dismantling_condition"),
        CheckConstraint("(received_at IS NULL AND part_id IS NULL) OR (received_at IS NOT NULL AND part_id IS NOT NULL)", name="ck_dismantling_receipt_link"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(100))
    included: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    catalog_key: Mapped[str] = mapped_column(String(100))
    category_key: Mapped[str] = mapped_column(String(100))
    category_name: Mapped[str] = mapped_column(String(100))
    subcategory_key: Mapped[str] = mapped_column(String(100))
    subcategory_name: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="unchecked")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    part_id: Mapped[str | None] = mapped_column(ForeignKey("parts.id"), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DismantlingCatalogSource(Base):
    __tablename__ = 'dismantling_catalog_sources'
    __table_args__ = (UniqueConstraint('account_id', 'source', name='uq_dcatalog_source'),
                     UniqueConstraint('id', 'account_id', name='uq_dcatalog_source_account'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    source: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[str] = mapped_column(Text)
    license_reference: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DismantlingCatalogType(Base):
    __tablename__ = 'dismantling_catalog_types'
    __table_args__ = (
        ForeignKeyConstraint(['source_id','account_id'], ['dismantling_catalog_sources.id','dismantling_catalog_sources.account_id'], name='fk_dcatalog_source_account'),
        UniqueConstraint('source_id','catalog_key',name='uq_dcatalog_type_key'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    catalog_key: Mapped[str] = mapped_column(String(100))
    category_key: Mapped[str] = mapped_column(String(100))
    category_name: Mapped[str] = mapped_column(String(100))
    subcategory_key: Mapped[str] = mapped_column(String(100))
    subcategory_name: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(100), default='')


class StockRequest(Base):
    """Replay protection only; Operation remains the single inventory ledger."""
    __tablename__ = 'stock_requests'
    __table_args__ = (UniqueConstraint('account_id','request_key',name='uq_stock_request_account_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    part_id: Mapped[str] = mapped_column(ForeignKey('parts.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    request_key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


from app.models.orders import Buyer, Order, OrderLine, OrderReservation, OrderEvent, OrderRequest  # noqa: E402,F401

# Expression indexes match the Smart Search migration, so Alembic check remains
# useful rather than hiding application-owned indexes from schema comparison.
from sqlalchemy import Index, func, literal_column, text  # noqa: E402
Index('ix_parts_smart_fts',func.to_tsvector(literal_column("'simple'::regconfig"),func.warehouse_search_text(Part.name)),postgresql_using='gin',postgresql_where=text('NOT archived'),_table=Part.__table__)
Index('ix_parts_smart_trgm',func.warehouse_search_text(Part.name).label('smart_name'),postgresql_using='gin',postgresql_ops={'smart_name':'gin_trgm_ops'},postgresql_where=text('NOT archived'))
Index('ix_parts_smart_oem_number',Part.account_id,func.warehouse_search_code(Part.oem_number),postgresql_where=text("NOT archived AND oem_number <> ''"))
Index('ix_parts_smart_article_number',Part.account_id,func.warehouse_search_code(Part.article_number),postgresql_where=text("NOT archived AND article_number <> ''"))
Index('ix_vehicle_smart_model',func.to_tsvector(literal_column("'simple'::regconfig"),func.warehouse_search_text(Vehicle.model)),postgresql_using='gin',_table=Vehicle.__table__)
Index('ix_vehicle_smart_brand',Vehicle.account_id,func.warehouse_search_text(Vehicle.manufacturer))


class TeamEvent(Base):
    __tablename__ = 'team_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    target_id: Mapped[str] = mapped_column(ForeignKey('accounts.id'))
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

from app.models.aleto import AletoModel, AletoOffer, AletoPrice, AletoApplication, AletoTaxonomy  # noqa: E402,F401
