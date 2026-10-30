"""Durable, tenant-owned analysis jobs. No stock/catalogue write relationships."""
from datetime import datetime
from sqlalchemy import String,Text,Integer,DateTime,JSON,ForeignKey,UniqueConstraint,CheckConstraint,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from app.db import Base
from app.models import uid,now

class ImportJob(Base):
    __tablename__='import_jobs'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    account_id:Mapped[str]=mapped_column(ForeignKey('accounts.id'),index=True)
    created_by:Mapped[str]=mapped_column(ForeignKey('accounts.id'))
    source:Mapped[str]=mapped_column(String(20),default='file')
    job_type:Mapped[str]=mapped_column(String(30))
    parameters:Mapped[dict]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(12),default='queued')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    progress_current:Mapped[int]=mapped_column(Integer,default=0)
    progress_total:Mapped[int|None]=mapped_column(Integer,nullable=True)
    phase:Mapped[str]=mapped_column(String(30),default='queued')
    result_summary:Mapped[dict]=mapped_column(JSON,default=dict)
    error_code:Mapped[str|None]=mapped_column(String(40),nullable=True)
    error_message:Mapped[str|None]=mapped_column(Text,nullable=True)
    lease_owner:Mapped[str|None]=mapped_column(String(36),nullable=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    attempt_count:Mapped[int]=mapped_column(Integer,default=0)
    retry_count:Mapped[int]=mapped_column(Integer,default=0)
    event_count:Mapped[int]=mapped_column(Integer,default=0)
    idempotency_key:Mapped[str]=mapped_column(String(36))
    fingerprint:Mapped[str]=mapped_column(String(64))
    context_hash:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('account_id','idempotency_key',name='uq_import_runner_request'),
        Index('uq_import_runner_active','account_id','context_hash',unique=True,postgresql_where=text("status IN ('queued','running')")),
        CheckConstraint("source='file' AND job_type IN ('file_validation','catalogue_preview')",name='ck_import_runner_type'),
        CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)",name='ck_import_runner_lease'),
        CheckConstraint("status IN ('queued','running','completed','failed','cancelled')",name='ck_import_runner_status'),
        CheckConstraint('attempt_count BETWEEN 0 AND 3 AND retry_count BETWEEN 0 AND 3 AND event_count>=0 AND progress_current>=0 AND (progress_total IS NULL OR progress_total>=progress_current)',name='ck_import_runner_bounds'))

class ImportJobEvent(Base):
    __tablename__='import_job_events'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    job_id:Mapped[str]=mapped_column(ForeignKey('import_jobs.id'),index=True)
    sequence:Mapped[int]=mapped_column(Integer)
    event_type:Mapped[str]=mapped_column(String(30))
    message:Mapped[str]=mapped_column(String(500))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    details:Mapped[dict]=mapped_column('metadata',JSON,default=dict)
    request_key:Mapped[str|None]=mapped_column(String(36),nullable=True)
    __table_args__=(UniqueConstraint('job_id','sequence',name='uq_import_runner_event'),UniqueConstraint('job_id','request_key',name='uq_import_runner_command'))
