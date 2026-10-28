"""Read-only observability. Never normalizes, enqueues, publishes or saves a plan."""
from sqlalchemy import select,func
from app.models.catalogue import CatalogueOffer, CataloguePath, CatalogueEntity
from app.models.canonical import CanonicalState,CanonicalMapping,CanonicalRun,CanonicalType,CanonicalPlacement
from app.services.canonical_rules import RULE_FINGERPRINT,RULES,UNIVERSAL


def diagnostics(db,vehicle=None):
    state=db.get(CanonicalState,1);sha=state.snapshot_sha if state else None
    mappings=select(CanonicalMapping).where(CanonicalMapping.snapshot_sha==sha).subquery()
    def count(cls):return db.scalar(select(func.count()).select_from(cls))
    published_run=db.scalar(select(CanonicalRun).where(CanonicalRun.mode=='publish',CanonicalRun.status=='done',CanonicalRun.snapshot_sha==sha).order_by(CanonicalRun.finished_at.desc()).limit(1)) if sha else None
    latest=db.scalar(select(CanonicalRun).order_by(CanonicalRun.created_at.desc(),CanonicalRun.id.desc()).limit(1))
    result=dict(catalogue_v2=dict(offers=count(CatalogueOffer),paths=count(CataloguePath),models=db.scalar(select(func.count()).select_from(CatalogueEntity).where(CatalogueEntity.kind=='model'))),
        canonical=dict(published=bool(sha),snapshot_sha=sha,rules_current=bool(sha and state.policy.get('rules_sha')==RULE_FINGERPRINT),
            published_rule_version=published_run.report.get('rule_version') if published_run else None,published_universal_version=published_run.report.get('universal_version') if published_run else None,
            executable_rule_version=RULES['version'],executable_universal_version=UNIVERSAL['version'],
            mapped_offers=db.scalar(select(func.count(func.distinct(CataloguePath.offer_id))).join(CanonicalMapping,CanonicalMapping.catalogue_path_id==CataloguePath.id).where(CanonicalMapping.snapshot_sha==sha,CanonicalMapping.type_id.is_not(None))) if sha else 0,
            types=db.scalar(select(func.count(func.distinct(mappings.c.type_id)))),placements=db.scalar(select(func.count(func.distinct(mappings.c.placement_id)))),
            unprocessed_records=db.scalar(select(func.count()).select_from(mappings).where(mappings.c.quality=='unprocessed')),
            review_records=db.scalar(select(func.count()).select_from(mappings).where(mappings.c.quality=='review')),
            stored_types=count(CanonicalType),stored_placements=count(CanonicalPlacement)),
        latest_run_id=latest.id if latest else None,read_only=True)
    if vehicle:
        from app.services.dismantling_preview import preview
        if sha and not result['canonical']['rules_current']:
            result['vehicle']=dict(id=vehicle.id,candidates=None,fallback_used=False,status='rules_stale',message='Потрібна нова перевірка та публікація правил')
        else:
            report=preview(db,vehicle,vehicle.account_id)
            result['vehicle']=dict(id=vehicle.id,candidates=report['total'],fallback_used=report['fallback_used'],published=report['published'],status=report['catalogue_status'])
    return result
