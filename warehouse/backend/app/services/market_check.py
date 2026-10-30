"""Explicit imported-catalogue check. External access remains disabled/fail-closed."""
from urllib.parse import urlsplit
from sqlalchemy import text
from app.services.price_guidance import parts_for,guidance,utcnow
from app.services.pricing import revisions
from app.services.catalogue_format import digest
from app.models import Vehicle
from app.services.inventory import snapshot


def source_url(value):
    try:
        u=urlsplit(value or '')
        return value if u.scheme=='https' and u.hostname in ('aleto.ua','www.aleto.ua') and u.port in (None,443) and not u.username and not u.password else None
    except ValueError:return None


def check(db,who,id):
    # Bound the synchronous local projection; never wait for an external service.
    db.execute(text("SELECT set_config('statement_timeout','5000',true)"))
    part=parts_for(db,who.workspace_account_id,[id])[0]
    vehicle=db.get(Vehicle,part.vehicle_id) if part.vehicle_id else None
    if vehicle and vehicle.account_id!=who.workspace_account_id:vehicle=None
    g=guidance(db,[part],who.workspace_account_id,include_historical=True)[id]
    # Link allowlist is presentation defense, not an HTTP fetch facility.
    rows=[*g.get('examples',[]),*g.get('historical_examples',[]),*[e for c in g['cohorts'] for e in c['examples']]]
    offers={}
    for e in rows:
        url=source_url(e['url'])
        if url:offers[(e['source'],e['article'],e['currency'])]={**e,'url':url}
    # Never show an aggregate as an Aleto result when its evidence links failed
    # the source allowlist. Do not recompute a median from a filtered subset.
    if any(not source_url(e['url']) for e in rows):
        g={**g,'level':'D','label':'Ціну не визначено','cohorts':[],'examples':[],'historical_examples':[],'offer_count':0,'example_count':0,'reasons':{**g.get('reasons',{}),'unverified_source_url':1}}
    checked=utcnow().isoformat()
    return dict(mode='imported_catalogue',status='completed' if offers else 'no_matches',fresh_data_fetched=False,live_refresh_available=False,
        checked_at=checked,observed_at=max((e['observed_at'] for e in offers.values()),default=None),cached=False,
        context_token=digest([who.workspace_account_id,snapshot(part),snapshot(vehicle) if vehicle else None,g]),
        part_revision=revisions(db,[part])[id],guidance=g,offers=list(offers.values()),
        offer_count=len({(e['source'],e['article']) for e in offers.values()}),
        source_status='source_unavailable',source_reason='Дозвіл на програмне отримання свіжих даних не підтверджено. Перевірено лише імпортований каталог.',
        external_url='https://aleto.ua/',search_text=' '.join(filter(None,[part.oem_number,vehicle.manufacturer if vehicle else None,vehicle.model if vehicle else None,part.name])))
