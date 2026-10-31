"""Global vehicle reference directory. It never owns or edits donor records."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, DateTime, Numeric, JSON, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class VehicleDirectoryVariant(Base):
    __tablename__ = 'vehicle_directory_variants'
    id: Mapped[str] = mapped_column(String(64),primary_key=True)
    brand: Mapped[str] = mapped_column(String(120),nullable=False)
    model: Mapped[str] = mapped_column(String(200),nullable=False)
    modification: Mapped[str] = mapped_column(String(350),nullable=False)
    year_from: Mapped[int|None] = mapped_column(Integer,nullable=True)
    year_to: Mapped[int|None] = mapped_column(Integer,nullable=True)
    displacement_l: Mapped[Decimal|None] = mapped_column(Numeric(4,1),nullable=True)
    fuel_type: Mapped[str|None] = mapped_column(String(50),nullable=True)
    power_kw: Mapped[int|None] = mapped_column(Integer,nullable=True)
    power_ps: Mapped[int|None] = mapped_column(Integer,nullable=True)
    body: Mapped[str|None] = mapped_column(String(180),nullable=True)
    drive_type: Mapped[str|None] = mapped_column(String(12),nullable=True)
    engine_codes: Mapped[list] = mapped_column(JSON,nullable=False,default=list)
    kba_numbers: Mapped[list] = mapped_column(JSON,nullable=False,default=list)
    source_sha: Mapped[str] = mapped_column(String(64),nullable=False)
    __table_args__ = (
        Index('ix_vehicle_directory_brand_model','brand','model'),
        Index('ix_vehicle_directory_years','year_from','year_to'),
        CheckConstraint('year_to IS NULL OR year_from IS NULL OR year_to >= year_from',name='ck_directory_year_range'),
        CheckConstraint('displacement_l IS NULL OR (displacement_l > 0 AND displacement_l <= 12)',name='ck_directory_displacement'),
    )

class VehicleDirectoryImport(Base):
    __tablename__ = 'vehicle_directory_imports'
    source_sha: Mapped[str] = mapped_column(String(64),primary_key=True)
    filename: Mapped[str] = mapped_column(String(200),nullable=False)
    record_count: Mapped[int] = mapped_column(Integer,nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer,nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
