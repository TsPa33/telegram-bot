from sqlalchemy import select, func, literal, case, and_, or_, not_, column, values, String, literal_column, union_all, text, cast
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.models import Part, Vehicle
from app.services.inventory import snapshot
from .query import parse, BRANDS, MODELS, DICTIONARY, TERMS, PAIRS, ts_group, FORMS, Plan, surface
from .normalize import normalize, identifier

REVISION='a73e05b9c842'
FEATURES=['tenant_ranked_parts','direction_constraints','dictionary_aliases','bounded_typo_search']

def vector(field):return func.to_tsvector(literal_column("'simple'::regconfig"),func.warehouse_search_text(field))
def match(field,query):return vector(field).op('@@')(func.to_tsquery(literal_column("'simple'::regconfig"),query))

def discover(db,account_id,tokens):
    # At most 36 role/token rows, not a list of donors or warehouse contents.
    if not tokens:return {}
    qt=values(column('token',String),name='search_tokens').data([(t,) for t in tokens])
    selects=[]
    for role,field in [('brand',Vehicle.manufacturer),('model',Vehicle.model),('generation',Vehicle.generation)]:
        predicate=match(field,qt.c.token) if role in ('brand','model') else func.warehouse_search_text(field)==qt.c.token
        found=select(Vehicle.id).where(Vehicle.account_id==account_id,predicate).correlate(qt).exists()
        selects.append(select(qt.c.token,literal(role).label('role')).where(found))
    result={}
    for token,role in db.execute(union_all(*selects)):result.setdefault(token,set()).add(role)
    return result

def aliases(kind,value):
    return list(dict.fromkeys([normalize(value),*[normalize(x) for x in DICTIONARY[kind].get(value,[])]]))

def search(db,account_id,*,q='',vehicle_id=None,manufacturer=None,model=None,in_stock=False,offset=0,limit=50):
    try:
        db.execute(text("SELECT set_config('statement_timeout','2500ms',true), "
                        "set_config('pg_trgm.word_similarity_threshold','0.60',true), "
                        "set_config('jit','off',true)"))
        basic=parse(q)
        identifier_only=False
        # Resolve a single actual identifier before treating e.g. X3 or A-2016
        # as donor/model/year words. Protected directions retain their meaning.
        if q.strip() and len(q.split())==1 and not any(g[3] for g in basic.groups):
            exact=select(Part.id).where(Part.account_id==account_id,not_(Part.archived))
            if in_stock:exact=exact.where(Part.quantity-Part.reserved_quantity>0,Part.assortment_enabled.is_(True))
            if vehicle_id:exact=exact.where(Part.vehicle_id==vehicle_id)
            if manufacturer is not None or model is not None:
                vehicle_scope=select(Vehicle.id).where(Vehicle.account_id==account_id)
                if manufacturer is not None:vehicle_scope=vehicle_scope.where(func.lower(Vehicle.manufacturer)==manufacturer.lower())
                if model is not None:vehicle_scope=vehicle_scope.where(func.lower(Vehicle.model)==model.lower())
                exact=exact.where(Part.vehicle_id.in_(vehicle_scope))
            identifier_only=bool(db.scalar(select(or_(*[exact.where(f!=literal_column("''"),func.warehouse_search_code(f)==identifier(q)).exists() for f in (Part.oem_number,Part.article_number)]))))
        plan=Plan(q,basic.tokens,codes=[identifier(q)]) if identifier_only else parse(q,discover(db,account_id,[t for t in basic.tokens if t not in FORMS]))
        if plan.clarify:return {'items':[],'total':0,'offset':offset,'limit':limit,'clarification':plan.clarify}
        name=func.warehouse_search_text(Part.name)
        scope=select(Part).where(Part.account_id==account_id,not_(Part.archived))
        if in_stock:scope=scope.where(Part.quantity-Part.reserved_quantity>0,Part.assortment_enabled.is_(True))
        if vehicle_id:scope=scope.where(Part.vehicle_id==vehicle_id)
        donors=select(Vehicle.id).where(Vehicle.account_id==account_id)
        car_constraints=[]
        for value in plan.brands:
            variants=aliases('brands',value)
            car_constraints.append(or_(*[match(Vehicle.manufacturer,' & '.join(v.split())) for v in variants]))
        for value in plan.models:car_constraints.append(match(Vehicle.model,value))
        for value in plan.generations:car_constraints.append(or_(func.warehouse_search_text(Vehicle.generation)==value,match(Vehicle.model,value)))
        for year in plan.years:car_constraints.append(Vehicle.year==year)
        if manufacturer is not None:car_constraints.append(func.lower(Vehicle.manufacturer)==manufacturer.lower())
        if model is not None:car_constraints.append(func.lower(Vehicle.model)==model.lower())
        if car_constraints:scope=scope.where(Part.vehicle_id.in_(donors.where(*car_constraints)))
        expanded=[];direct=[];strict=[];fuzzy=[];typos=[]
        concepts={g[2] for g in plan.groups};powertrain_used=False
        for token,query,concept,protected in plan.groups:
            hit=match(Part.name,query);direct.append(match(Part.name,token))
            powertrain=None
            if concept in ('diesel','petrol') or (protected and not concept) or ('engine' in concepts and any(c.isdigit() for c in token)):
                powertrain=Vehicle.engine+literal(' ')+Vehicle.fuel_type
            elif concept in ('auto','manual') and 'gearbox' in concepts:
                powertrain=Vehicle.transmission
            if powertrain is not None:
                powertrain_used=True
                hit=or_(hit,Part.vehicle_id.in_(donors.where(match(powertrain,query))))
            if protected:
                strict.append(hit)
                if concept in PAIRS:
                    opposite=match(Part.name,ts_group(TERMS[PAIRS[concept]]['targets']))
                    if powertrain is not None:opposite=or_(opposite,Part.vehicle_id.in_(donors.where(match(powertrain,ts_group(TERMS[PAIRS[concept]]['targets'])))))
                    strict.append(not_(opposite))
            typo=name.op('%>')(token) if len(token)>=5 and token.isalpha() and not protected and not concept else literal(False)
            expanded.append(or_(hit,typo));fuzzy.append(hit if concept or powertrain is not None else match(Part.name,token));typos.append(typo)
        # Identifier atoms with digits are NOT extra textual constraints. Exact
        # identifier matching still obeys all explicit donor and protected groups.
        code=or_(*[and_(field!=literal_column("''"),func.warehouse_search_code(field).in_(plan.codes)) for field in [Part.oem_number,Part.article_number]]) if plan.codes and q.strip() else literal(False)
        lexical=and_(*expanded) if expanded else literal(bool(q.strip()) and bool(car_constraints))
        direct_all=and_(*direct) if direct else literal(False)
        expanded_all=and_(*fuzzy) if fuzzy else literal(False)
        full_name=normalize(q)
        clean_name=' '.join(t for t,_,_,_ in plan.groups)
        if identifier_only:predicate=code
        elif not q.strip():predicate=literal(True)
        else:predicate=or_(code,lexical)
        scope=scope.where(predicate,*strict)
        score=case((code,1000),(name==full_name,900),(and_(name==clean_name,literal(bool(car_constraints))),850),
                   (name==clean_name,825),(direct_all,800),(expanded_all,700),(and_(lexical,or_(literal(False),*typos)),600),else_=500).label('relevance')
        if not q.strip():score=literal(0).label('relevance')
        total=db.scalar(select(func.count()).select_from(scope.subquery()))
        result=db.execute(scope.add_columns(score,code.label('code_match'),expanded_all.label('terms_match')).order_by(score.desc(),Part.id).offset(offset).limit(limit)).all()
        donor_ids={p.vehicle_id for p,*_ in result if p.vehicle_id}
        real_donors={v.id:{k:getattr(v,k) for k in ['id','manufacturer','model','generation','year','number']} for v in db.scalars(select(Vehicle).where(Vehicle.account_id==account_id,Vehicle.id.in_(donor_ids)))} if donor_ids else {}
        items=[]
        for part,rank,is_code,terms_match in result:
            if is_code:why='Точний OEM або артикул (без урахування роздільників).'
            elif rank>=825:why='Збіг назви'+(' та автомобіля.' if car_constraints else '.')
            elif rank==800:why='Збіг слів назви; порядок слів не впливає.'
            elif terms_match:
                mapped=[f'«{surface(plan.raw,token)}» → «{TERMS[concept]["label"]}»' for token,_,concept,_ in plan.groups if concept and token in plan.tokens and not TERMS[concept].get('protected')]
                why='Збіг за словником: '+', '.join(mapped) if mapped else 'Збіг нормалізованих слів.'
                if powertrain_used:why+=' Тип — за назвою або даними донора.'
            elif not plan.groups and car_constraints:why='Запчастини зазначеного автомобіля-донора.'
            elif rank==600:why='Можлива помилка або неповне слово; перевірте назву деталі.'
            else:why='Частковий збіг назви.'
            items.append({**snapshot(part),'available_quantity':part.available_quantity,'donor':real_donors.get(part.vehicle_id),
                'relevance':rank,'match_explanation':why})
        return {'items':items,'total':total,'offset':offset,'limit':limit,'clarification':None}
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig,'sqlstate',None)=='57014':raise HTTPException(503,'Пошук перевищив ліміт часу. Уточніть запит.') from None
        raise HTTPException(503,'Розумний пошук тимчасово недоступний. Скористайтеся стандартним.') from None
