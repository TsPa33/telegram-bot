"""Additive v3 reference layer. No relationship to stock or donor-plan mutation."""
from datetime import datetime
from sqlalchemy import String,Text,JSON,Integer,DateTime,ForeignKey,ForeignKeyConstraint,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import uid,now

class CanonicalType(Base):
    __tablename__='canonical_types'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    identity_key:Mapped[str]=mapped_column(String(64),unique=True)
    name:Mapped[str]=mapped_column(String(200))
    category:Mapped[str]=mapped_column(String(200))
    subcategory:Mapped[str]=mapped_column(String(200))
    provenance:Mapped[dict]=mapped_column(JSON)

class CanonicalPlacement(Base):
    __tablename__='canonical_placements'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    type_id:Mapped[str]=mapped_column(ForeignKey('canonical_types.id'),index=True)
    identity_key:Mapped[str]=mapped_column(String(64),unique=True)
    details:Mapped[dict]=mapped_column(JSON)
    side:Mapped[str]=mapped_column(String(20))
    position:Mapped[str]=mapped_column(String(20))
    __table_args__=(UniqueConstraint('id','type_id'),
        CheckConstraint("side IN ('left','right','unknown') AND position IN ('front','rear','unknown')",name='ck_canonical_placement'),)

class CanonicalVariant(Base):
    __tablename__='canonical_variants'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    type_id:Mapped[str]=mapped_column(String(36),index=True)
    placement_id:Mapped[str]=mapped_column(String(36),index=True)
    oem:Mapped[str|None]=mapped_column(Text,nullable=True)
    attributes:Mapped[dict]=mapped_column(JSON)
    __table_args__=(ForeignKeyConstraint(['placement_id','type_id'],['canonical_placements.id','canonical_placements.type_id']),
        UniqueConstraint('id','type_id','placement_id'),)

class CanonicalAlias(Base):
    __tablename__='canonical_aliases'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    series_key:Mapped[str]=mapped_column(String(64),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    type_id:Mapped[str|None]=mapped_column(ForeignKey('canonical_types.id'),nullable=True)
    enabled:Mapped[bool]=mapped_column(default=True)
    criteria:Mapped[dict]=mapped_column(JSON)
    evidence:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('series_key','revision'),CheckConstraint('revision>0 AND (NOT enabled OR type_id IS NOT NULL)',name='ck_canonical_alias'),)

class CanonicalFitment(Base):
    __tablename__='canonical_fitments'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    variant_id:Mapped[str]=mapped_column(ForeignKey('canonical_variants.id'),index=True)
    criteria:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(20))
    evidence:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(CheckConstraint("status IN ('confirmed','incompatible')",name='ck_canonical_fitment'),)

class CanonicalRun(Base):
    __tablename__='canonical_runs'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    actor_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    session_hash:Mapped[str]=mapped_column(String(64))
    mode:Mapped[str]=mapped_column(String(10))
    status:Mapped[str]=mapped_column(String(10),default='queued')
    preview_id:Mapped[str|None]=mapped_column(ForeignKey('canonical_runs.id'),nullable=True)
    token:Mapped[str|None]=mapped_column(String(64),nullable=True)
    snapshot_sha:Mapped[str|None]=mapped_column(String(64),nullable=True)
    report:Mapped[dict]=mapped_column(JSON,default=dict)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(CheckConstraint("mode IN ('preview','publish') AND status IN ('queued','running','done','error')",name='ck_canonical_run'),)

class CanonicalState(Base):
    __tablename__='canonical_state'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    snapshot_sha:Mapped[str|None]=mapped_column(String(64),nullable=True)
    policy:Mapped[dict]=mapped_column(JSON,default=dict)
    __table_args__=(CheckConstraint('id=1',name='ck_canonical_state'),)

class CanonicalMapping(Base):
    __tablename__='canonical_mappings'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    snapshot_sha:Mapped[str]=mapped_column(String(64),index=True)
    source_kind:Mapped[str]=mapped_column(String(10))
    source_key:Mapped[str]=mapped_column(String(200))
    source_sha:Mapped[str]=mapped_column(String(64))
    catalogue_path_id:Mapped[str|None]=mapped_column(ForeignKey('catalogue_paths.id'),nullable=True,index=True)
    type_id:Mapped[str|None]=mapped_column(ForeignKey('canonical_types.id'),nullable=True,index=True)
    placement_id:Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    variant_id:Mapped[str|None]=mapped_column(String(36),nullable=True)
    quality:Mapped[str]=mapped_column(String(20))
    evidence:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('snapshot_sha','source_kind','source_key'),
        ForeignKeyConstraint(['placement_id','type_id'],['canonical_placements.id','canonical_placements.type_id']),
        ForeignKeyConstraint(['variant_id','type_id','placement_id'],['canonical_variants.id','canonical_variants.type_id','canonical_variants.placement_id']),
        CheckConstraint("source_kind IN ('base','v2') AND quality IN ('verified_rule','verified_owner','review','unprocessed')",name='ck_canonical_mapping_quality'),
        CheckConstraint("(quality IN ('review','unprocessed') AND type_id IS NULL AND placement_id IS NULL AND variant_id IS NULL) OR (quality IN ('verified_rule','verified_owner') AND type_id IS NOT NULL AND placement_id IS NOT NULL)",name='ck_canonical_mapping_target'),)
