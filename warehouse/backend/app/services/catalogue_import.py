"""One transactional planner for persisted preview and explicit global apply."""
from collections import Counter, defaultdict
from app.services.catalogue_language_gate import needs_ukrainian_review
from app.services.catalogue_uk_suggestions import ukrainian_name_proposal
import hmac
import os
from uuid import uuid5, NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import select, text, insert, tuple_
from app.models import Account, Session as AuthSession, now
from app.models.catalogue import (CatalogueEntity as Entity, CatalogueAlias as Alias, CatalogueSource as Source,
    CatalogueOffer as Offer, CataloguePrice as Price, CatalogueApplication as Application,
    CataloguePath as Path, CatalogueState as State, CatalogueJob as Job)
from app.services.aleto_import import identity, observation, money
from app.services.catalogue_format import digest

LOCK = 0x43415456320001
KINDS = {'manufacturer','model','category','subcategory','part_type'}
COUNTERS = ('manufacturers','models','categories','subcategories','part_types','sources','offers','prices','applications','paths','aliases')
AMBIGUOUS = {identity(n) for n in ('Комп','Деталь','Інше','Другое','Unknown','?','Невідомо')}


def platform_admin(user):
    allowed={v.strip() for v in os.getenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS','').split(',') if v.strip()}
    return bool(user and user.id in allowed and user.role=='DIRECTOR' and user.is_active and not user.workspace_account_id)


def require_admin(db, who):
    user=db.scalar(select(Account).where(Account.id==who.actor_id).with_for_update(read=True).execution_options(populate_existing=True))
    session=db.scalar(select(AuthSession).where(AuthSession.token_hash==who.session.token_hash).execution_options(populate_existing=True))
    if not session or session.expires_at<=now():raise HTTPException(401,'Сесію відкликано')
    if who.actor_id!=who.user.id or not platform_admin(user):
        raise HTTPException(403,'Глобальний імпорт доступний лише власнику платформи з серверного allowlist')
    return user


def stable(key):
    return str(uuid5(NAMESPACE_URL,'carpot.catalogue.v2:'+key))


def normalized_details(details):
    return {k:identity(v) if isinstance(v,str) else v for k,v in details.items()}


class Planner:
    def __init__(self,db,actor,resolutions,progress=None,write=True,rows=None):
        self.db,self.actor,self.resolutions=db,actor,resolutions
        self.write=write
        self.progress=progress or (lambda done,total,phase: None)
        self.pending=defaultdict(list)
        self.entities={e.identity_key:e for e in db.scalars(select(Entity).order_by(Entity.id))}
        self.by_id={e.id:e for e in self.entities.values()}
        self.aliases={(a.kind,a.context_id,a.alias_key):a for a in db.scalars(select(Alias))}
        self.sources={s.name:s for s in db.scalars(select(Source))}
        # Price history and paths can grow indefinitely. Load only offers
        # referenced by this job; retain the full entity/alias index for manual
        # merges against existing canonical targets. Never query per input row.
        if rows is None:
            offers=list(db.scalars(select(Offer)))
        else:
            keys=list({(self.sources[r['source']].id,r['source_article']) for r in rows if r['source'] in self.sources})
            offers=[]
            for start in range(0,len(keys),500):
                offers.extend(db.scalars(select(Offer).where(tuple_(Offer.source_id,Offer.source_article).in_(keys[start:start+500]))))
        self.offers={(o.source_id,o.source_article):o for o in offers}
        ids=[o.id for o in offers];prices=[];applications=[];paths=[]
        for start in range(0,len(ids),500):
            batch=ids[start:start+500]
            prices.extend(db.scalars(select(Price).where(Price.offer_id.in_(batch))))
            applications.extend(db.execute(select(Application.offer_id,Application.model_id).where(Application.offer_id.in_(batch))))
            paths.extend(db.scalars(select(Path).where(Path.offer_id.in_(batch))))
        self.prices={(p.offer_id,p.observed_at):p for p in prices}
        self.applications=set(applications)
        self.paths={p.id:p for p in paths}
        self.existing_ids=set(self.by_id)
        self.candidate_index=defaultdict(list)
        for e in self.by_id.values():
            candidates=self.candidate_index[(e.kind,e.parent_id)]
            if len(candidates)<25:candidates.append(dict(id=e.id,name=e.name,details=e.details))
        self.suggestions={};self.cache={};self.issues={};self.counts={name:Counter() for name in COUNTERS};self.used=set();self.skipped=0;self.price_changes=[]

    def stage(self,obj):
        # Deterministic IDs allow FK-ordered batches without per-row round trips.
        self.pending[type(obj)].append(obj)

    def persist(self):
        # Preview runs the identical planner but need not insert speculative rows
        # merely to roll them back. The surrounding savepoint still expires any
        # attached existing objects changed by planning. Apply checks all DB FKs.
        if not self.write:return
        groups=[(Source,self.pending[Source])]
        groups += [(Entity,[e for e in self.pending[Entity] if e.kind==kind])
                   for kind in ('manufacturer','category','model','subcategory','part_type')]
        groups += [(cls,self.pending[cls]) for cls in (Offer,Price,Application,Path,Alias)]
        with self.db.no_autoflush:
            for cls,objects in groups:
                for start in range(0,len(objects),500):
                    values=[{k:v for k,v in obj.__dict__.items() if not k.startswith('_')}
                            for obj in objects[start:start+500]]
                    self.db.execute(insert(cls),values)
        self.db.flush()

    def bump(self,name,action):self.counts[name][action]+=1

    def issue(self,key,kind,name,reason,parent=None,actions=None):
        if key not in self.issues:
            candidates=self.candidate_index.get((kind,parent),[]) if kind in KINDS else []
            self.issues[key]=dict(key=key,kind=kind,name=name,reason=reason,candidates=candidates,
                                  allowed_actions=actions or ['target','create_name','skip'],rows=0,parent_id=parent)
        self.issues[key]['rows']+=1

    def entity(self,kind,name,parent=None,details=None,review=False,verified=False):
        details=details or {}
        context=parent.id if parent else ''
        alias_key=digest([identity(name),normalized_details(details)])
        key=digest([kind,context,alias_key])
        if key in self.cache and (self.cache[key] is not None or not verified):return self.cache[key]
        decision=None if verified else self.resolutions.get(key)
        if decision:
            self.used.add(key)
            if decision.get('action')=='skip':
                self.cache[key]=None;return None
            if decision.get('action')=='target':
                target=self.by_id.get(decision.get('target_id'))
                if not target or target.id not in self.existing_ids or target.kind!=kind or (target.parent_id or '')!=context:
                    raise ValueError('Alias target must exist with the same kind and parent')
                chosen=target
            elif decision.get('action')=='create_name':
                new=decision.get('name','').strip()
                if not new or len(new)>1000 or any(ord(c)<32 for c in new) or identity(new) in AMBIGUOUS or (kind in ('category','subcategory','part_type') and needs_ukrainian_review(new)):
                    raise ValueError('Provide an explicit unambiguous verified name')
                chosen=self.entity(kind,new,parent,details,False,verified=True)
            else:raise ValueError('Unsupported entity resolution')
            alias=self.aliases.get((kind,context,alias_key))
            if alias and alias.target_id!=chosen.id:raise ValueError('Verified alias already points to a different target')
            if not alias:
                alias=Alias(kind=kind,context_id=context,alias_key=alias_key,source_name=name,
                            target_id=chosen.id,verified_by=self.actor)
                self.stage(alias);self.aliases[(kind,context,alias_key)]=alias;self.bump('aliases','inserted')
            self.cache[key]=chosen;return chosen
        alias=self.aliases.get((kind,context,alias_key))
        if alias:
            chosen=self.by_id[alias.target_id]
            if (chosen.parent_id or '')!=context:raise ValueError('Verified alias parent mismatch')
            self.cache[key]=chosen;return chosen
        chosen=self.entities.get(key)
        if chosen:
            self.bump(kind+'s' if kind not in ('category','subcategory') else {'category':'categories','subcategory':'subcategories'}[kind],'unchanged')
        elif review or identity(name) in AMBIGUOUS or (kind in ('category','subcategory','part_type') and (needs_ukrainian_review(name) or (ukrainian_name_proposal(name) is not None and ukrainian_name_proposal(name) != name) or any(existing.kind==kind and (existing.parent_id or '')==context and identity(existing.name)==identity(name) for existing in self.by_id.values()))):
            reason=('Російськомовна або змішана назва: виберіть український канонічний запис чи створіть перевірену українську назву' if needs_ukrainian_review(name) else 'Можливий дублікат або неоднозначна назва: перевірте наявні типи, оберіть target чи створіть перевірений запис')
            self.issue(key,kind,name,reason,parent.id if parent else None)
            if kind in ('category','subcategory','part_type'):
                proposal=ukrainian_name_proposal(name)
                if proposal and proposal != name:
                    self.issues[key]['suggested_uk_name']=proposal
                    self.issues[key]['suggestion_status']='requires_admin_approval'
            self.cache[key]=None;return None
        else:
            self.suggestions[key]=dict(key=key,kind=kind,name=name,reason='Новий запис; за потреби підтвердьте об’єднання з наявним',
                allowed_actions=['target','create_name','skip'],rows=1,parent_id=parent.id if parent else None,
                candidates=self.candidate_index.get((kind,parent.id if parent else None),[]))
            chosen=Entity(id=stable(key),kind=kind,parent_id=parent.id if parent else None,
                          parent_kind=parent.kind if parent else None,name=name,normalized_name=identity(name),identity_key=key,details=details)
            self.stage(chosen)
            self.entities[key]=chosen;self.by_id[chosen.id]=chosen
            self.bump(kind+'s' if kind not in ('category','subcategory') else {'category':'categories','subcategory':'subcategories'}[kind],'inserted')
        self.cache[key]=chosen;return chosen

    def run(self,rows):
        groups=defaultdict(list)
        for row in rows:groups[(row['source'],row['source_article'])].append(row)
        for index,((source,article),items) in enumerate(groups.items()):
            if index%250==0:self.progress(index,len(groups),"planning")
            skey=digest(['source',source])
            if source not in self.sources:
                self.sources[source]=Source(id=stable(skey),name=source);self.stage(self.sources[source]);self.bump('sources','inserted')
            elif source not in self.cache:self.bump('sources','unchanged')
            self.cache[source]=True
            src=self.sources[source]
            existing=self.offers.get((src.id,article))
            issue_key=digest(['offer',source,article])
            decision=self.resolutions.get(issue_key,{})
            if decision:
                self.used.add(issue_key)
                if decision.get('action')=='skip':self.skipped+=len(items);continue
                if decision.get('action') not in ('keep_existing','accept_incoming'):raise ValueError('Unsupported offer decision')
            def properties(row):return {k:row[k] for k in ('part_name','oem','condition','source_url','side','position')}
            props={digest(properties(r)) for r in items}
            observations={}
            bad_price=False
            for row in items:
                date=observation(row['observed_at'])
                value=(money(row['price_uah']),money(row['price_usd']),row['source_url'])
                if date in observations and observations[date]!=value:bad_price=True
                observations[date]=value
            if len(props)>1 or bad_price:
                self.issue(issue_key,'offer',source+':'+article,'Суперечливі властивості або ціни одного артикулу всередині файла',actions=['skip'])
                self.issues[issue_key]['incoming_examples']=[{k:r[k] for k in ('part_name','oem','condition','side','position','price_uah','price_usd','observed_at')} for r in items[:2]]
                continue
            latest=max(items,key=lambda r:r['observed_at'])
            incoming=properties(latest)
            if existing and existing.properties!=incoming and not decision:
                self.issue(issue_key,'offer',source+':'+article,'Властивості відрізняються від збереженої пропозиції',actions=['keep_existing','accept_incoming','skip'])
                self.issues[issue_key].update(existing=existing.properties,incoming=incoming)
                continue
            # An observation is immutable even when metadata replacement is approved.
            if existing and any((existing.id,date) in self.prices and
                (self.prices[existing.id,date].price_uah,self.prices[existing.id,date].price_usd,self.prices[existing.id,date].source_url)!=value
                for date,value in observations.items()):
                self.issue(issue_key,'offer',source+':'+article,'Конфлікт незмінюваного спостереження за тією самою датою',actions=['skip']);continue
            previous=self.prices.get((existing.id,existing.observed_at)) if existing else None
            observed=observation(latest['observed_at'])
            if existing is None:
                key=digest(['offer',src.id,article])
                existing=Offer(id=stable(key),source_id=src.id,source_article=article,properties=incoming,observed_at=observed)
                self.stage(existing);self.offers[(src.id,article)]=existing;self.bump('offers','inserted')
            else:
                changed=False
                if observed>existing.observed_at:existing.observed_at=observed;changed=True
                if decision.get('action')=='accept_incoming' and incoming!=existing.properties:
                    existing.properties=incoming;changed=True
                self.bump('offers','updated' if changed else 'unchanged')
            for date,(uah,usd,url) in observations.items():
                if (existing.id,date) in self.prices:self.bump('prices','unchanged')
                else:
                    p=Price(id=stable(digest(['price',existing.id,date.isoformat()])),offer_id=existing.id,
                            observed_at=date,price_uah=uah,price_usd=usd,source_url=url)
                    self.stage(p);self.prices[(existing.id,date)]=p;self.bump('prices','inserted')
                    if len(self.price_changes)<50:
                        self.price_changes.append(dict(source=source,source_article=article,observed_at=date.isoformat(),
                            price_uah=str(uah) if uah is not None else None,price_usd=str(usd) if usd is not None else None,
                            previous_uah=str(previous.price_uah) if previous and previous.price_uah is not None else None,
                            previous_usd=str(previous.price_usd) if previous and previous.price_usd is not None else None))
            for row in items:
                manufacturer=self.entity('manufacturer',row['manufacturer'])
                model=self.entity('model',row['model'],manufacturer,{'generation':row['generation']}) if manufacturer else None
                if not model:
                    self.skipped+=1
                    continue
                application=(existing.id,model.id)
                if application not in self.applications:
                    self.stage(Application(offer_id=existing.id,model_id=model.id))
                    self.applications.add(application);self.bump('applications','inserted')
                elif application not in self.cache:self.bump('applications','unchanged')
                self.cache[application]=True
                category=self.entity('category',row['category'],review=row.get('_review_category',False))
                sub=self.entity('subcategory',row['subcategory'],category,review=row.get('_review_subcategory',False)) if category else None
                traits={k:row[k] for k in ('oem','side','position')}
                part=self.entity('part_type',row['part_name'],sub,traits) if sub else None
                if not part:self.skipped+=1
                raw={k:row[k] for k in ('manufacturer','model','category','subcategory','part_name','oem','side','position','generation','year_from','year_to')}
                raw['year_compatibility']='unverified'
                raw['source_category']=row.get('_raw_category',row['category'])
                raw['source_subcategory']=row.get('_raw_subcategory',row['subcategory'])
                path_key=digest(raw)
                pid=stable(digest(['path',existing.id,model.id,path_key]))
                old=self.paths.get(pid)
                if old is None:
                    old=Path(id=pid,offer_id=existing.id,model_id=model.id,part_type_id=part.id if part else None,
                             part_kind='part_type' if part else None,path_key=path_key,raw=raw)
                    self.stage(old);self.paths[pid]=old;self.bump('paths','inserted')
                elif part is not None and old.part_type_id!=part.id:
                    # Explicitly resolved taxonomy may enrich a previously pending path.
                    old.part_type_id=part.id if part else None;old.part_kind='part_type' if part else None;self.bump('paths','updated')
                elif pid not in self.cache:self.bump('paths','unchanged')
                self.cache[pid]=True
        self.progress(len(groups),len(groups),"writing" if self.write else "validating")
        self.persist()
        unused=set(self.resolutions)-self.used
        if unused:raise ValueError('Resolution no longer matches the validated input; remove unused decisions')
        issues=list(self.issues.values())
        suggestions=sorted(self.suggestions.values(),key=lambda s: ['manufacturer','model','category','subcategory','part_type'].index(s['kind']))
        return dict(price_changes=self.price_changes,suggestions=suggestions[:200],suggestion_total=len(suggestions),counts={k:{a:c[a] for a in ('inserted','updated','unchanged')} for k,c in self.counts.items()},
                    issues=issues[:200],unresolved_total=len(issues),issues_truncated=len(issues)>200,
                    skipped_rows=self.skipped,input_rows=len(rows),year_compatibility='unverified',mode='preview',committed=False)


def locked_job(db,id):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
    job=db.scalar(select(Job).where(Job.id==id).with_for_update().execution_options(populate_existing=True))
    if not job:raise HTTPException(404,'Import job не знайдено')
    if job.status=='failed':raise HTTPException(409,'Завантажте новий перевірений файл')
    if digest(job.rows)!=job.payload_sha256:raise HTTPException(409,'Перевірені дані job пошкоджено')
    state=db.get(State,1,populate_existing=True)
    if state is None:raise HTTPException(503,'Catalogue state відсутній; перевірте міграцію')
    return job,state


def preview(db,id,actor,resolutions,progress=None):
    job,state=locked_job(db,id)
    if job.status=='applied':raise HTTPException(409,'Імпорт уже застосовано; створіть новий job')
    nested=db.begin_nested()
    try:result=Planner(db,actor,resolutions,progress,write=False,rows=job.rows).run(job.rows)
    finally:nested.rollback()
    # Savepoint rollback expires only speculative global entities, not the job.
    job.resolutions=resolutions;job.report=result;job.catalogue_revision=state.revision
    job.preview_token=digest([job.payload_sha256,resolutions,state.revision,result])
    job.status='review' if result['unresolved_total'] else 'ready'
    return job


def apply(db,id,actor,token,progress=None):
    job,state=locked_job(db,id)
    if job.status=='applied':
        if not hmac.compare_digest(job.preview_token or '',token):raise HTTPException(409,'Невірний preview token')
        return job
    if job.status!='ready' or not hmac.compare_digest(job.preview_token or '',token) or job.catalogue_revision!=state.revision:
        raise HTTPException(409,'Потрібен новий preview: дані, рішення або каталог змінилися')
    expected=digest([job.payload_sha256,job.resolutions,state.revision,job.report])
    if not hmac.compare_digest(expected,token):raise HTTPException(409,'Preview не відповідає даним')
    result=Planner(db,actor,job.resolutions,progress,rows=job.rows).run(job.rows)
    if result!=job.report or result['unresolved_total']:raise HTTPException(409,'План змінився; потрібен новий preview')
    if any(c['inserted'] or c['updated'] for c in result['counts'].values()):state.revision+=1
    job.status='applied';job.applied_at=now()
    job.report={**result,'mode':'apply','committed':True,'applied_by':actor}
    return job
