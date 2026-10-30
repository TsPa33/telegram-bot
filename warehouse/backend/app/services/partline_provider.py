"""PartLine integration preparation: live BLOCKED, synthetic XML contract only.

Official GetPrice docs/auth/reuse terms could not be retrieved (proxy CONNECT 403).
The XML below is our explicit test envelope, NOT a guessed PartLine response.
No HTTP client, credentials, live activation flag or catalogue/pricing writes.
"""
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from pathlib import Path
import hashlib,json,re,time,math
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

VERSION='carpot-partline-fixture-v1'
FIXTURE=Path(__file__).with_name('partline_fixtures')/'prices.xml'
DOC_URL='https://partline.com.ua/api/GetPrice'
MAX_BYTES=131072
MAX_OFFERS=100
TIMEOUT_SECONDS=10
PROVIDER_SLOT=0x52383400

class ProviderError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)

MESSAGES={
 'PARTLINE_ACCESS_UNVERIFIED':'PartLine: live-доступ, контракт API та умови використання ще не підтверджені.',
 'PARTLINE_TIMEOUT':'Перевищено ліміт часу тестового каналу PartLine. Live-запит не виконувався.',
 'PARTLINE_AUTH_ERROR':'Тестовий канал повернув помилку авторизації. Live-доступ не перевірено.',
 'PARTLINE_REJECTED':'Тестовий канал відхилив запит. Live-доступ не перевірено.',
 'PARTLINE_INVALID_XML':'Некоректний або небезпечний тестовий XML.',
 'PARTLINE_INVALID_OFFER':'Некоректна ціна, валюта або інші поля тестової пропозиції.',
 'PARTLINE_RESPONSE_LIMIT':'Тестовий результат перевищує встановлений ліміт.',
 'PARTLINE_FIXTURE_CHANGED':'Тестовий fixture змінився; створіть нову задачу.',
 'PARTLINE_STORAGE_UNAVAILABLE':'Тестовий XML-fixture недоступний worker.',
 'PARTLINE_BUSY':'Інша тестова задача PartLine виконується. Повторіть пізніше.',
}


def capabilities():
    return dict(source='partline',source_type='new_parts',status='blocked',live_enabled=False,access_confirmed=False,contract_verified=False,worker_connection_verified=False,fixture_enabled=True,documentation_url=DOC_URL,blockers=['documentation_unavailable','auth_unverified','reuse_terms_unverified','test_access_unverified','cloud_worker_unverified'],limits=dict(articles_per_job=1,fixture_jobs_per_account_per_hour=5,fixture_jobs_globally_per_hour=20,provider_concurrency=1,max_attempts=3,max_response_bytes=MAX_BYTES,timeout_seconds=TIMEOUT_SECONDS),message=MESSAGES['PARTLINE_ACCESS_UNVERIFIED'])


def validate_reference_url(value):
    """Identifier guard for future review, not permission to send a request."""
    try:
        p=urlsplit(value)
        if value!=DOC_URL or p.scheme!='https' or p.hostname!='partline.com.ua' or p.port is not None or p.username or p.password or p.query or p.fragment:raise ValueError()
    except (ValueError,TypeError):raise ProviderError('PARTLINE_ACCESS_UNVERIFIED') from None
    return value


def live_lookup(*args,**kwargs):
    # Cannot be enabled by env variables or client parameters before contract review.
    raise ProviderError('PARTLINE_ACCESS_UNVERIFIED')


def query_text(value,optional=False):
    if optional and value in ('',None):return ''
    if not isinstance(value,str):raise ValueError('Invalid query')
    value=value.strip()
    if not 1<=len(value)<=100 or any(ord(c)<32 or ord(c)==127 for c in value) or any(c in value for c in '<>\\\r\n') or '://' in value:raise ValueError('Invalid query')
    return value


def fixture_bytes():
    try:raw=FIXTURE.read_bytes()
    except OSError:raise ProviderError('PARTLINE_STORAGE_UNAVAILABLE') from None
    if len(raw)>MAX_BYTES:raise ProviderError('PARTLINE_RESPONSE_LIMIT')
    return raw,hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class TestResponse:
    """Injected test-only response envelope, not an official HTTP contract."""
    body:bytes
    status:int=200
    elapsed_seconds:float=0
    content_type:str='application/xml'


def parse_fixture(response,article,manufacturer='',progress=lambda *a:None):
    article=query_text(article);manufacturer=query_text(manufacturer,True)
    if not isinstance(response.elapsed_seconds,(float,int)) or not math.isfinite(response.elapsed_seconds) or response.elapsed_seconds>TIMEOUT_SECONDS or response.elapsed_seconds<0:raise ProviderError('PARTLINE_TIMEOUT')
    if response.status in (401,403):raise ProviderError('PARTLINE_AUTH_ERROR')
    if response.status!=200:raise ProviderError('PARTLINE_REJECTED')
    raw=response.body
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ProviderError('PARTLINE_RESPONSE_LIMIT')
    if response.content_type.split(';',1)[0].strip().lower() not in ('application/xml','text/xml'):raise ProviderError('PARTLINE_INVALID_XML')
    try:
        xml=raw.decode('utf-8-sig')
        # UTF-8 only, reject declarations before parsing. No DTD/entities/XInclude.
        if '\x00' in xml or re.search(r'<!\s*(?:DOCTYPE|ENTITY)',xml,re.I):raise ValueError()
        root=ET.fromstring(xml)
        if root.tag!='carpot-partline-fixture' or root.attrib!={'version':VERSION,'synthetic':'true'}:raise ValueError()
        if len(list(root))>MAX_OFFERS:raise ProviderError('PARTLINE_RESPONSE_LIMIT')
        def check(node,depth=0):
            if depth>8 or len(list(node))>MAX_OFFERS:raise ValueError()
            if '{' in node.tag:raise ValueError()
            for child in node:check(child,depth+1)
        check(root)
    except (UnicodeError,ET.ParseError,ValueError,RecursionError):raise ProviderError('PARTLINE_INVALID_XML') from None
    offers=[];seen=set();duplicates=0
    for index,node in enumerate(root,1):
        progress(index,len(root),'offers')
        try:
            if node.tag!='offer' or node.attrib:raise ValueError()
            expected={'article','manufacturer','name','price','currency','quantity','availability'}
            values={n.tag:n.text or '' for n in node}
            if len(values)!=len(node) or set(values)!=expected or any(len(v)>1000 for v in values.values()) or any(n.attrib or len(n) for n in node):raise ValueError()
            values={k:v.strip() for k,v in values.items()}
            number=query_text(values['article']);brand=query_text(values['manufacturer'],True)
            if not values['name'] or any(ord(c)<32 or ord(c)==127 for c in ''.join(values.values())):raise ValueError()
            price_text=values['price']
            if not re.fullmatch(r'\d{1,10}(?:\.\d{1,2})?',price_text):raise ValueError()
            price=Decimal(price_text)
            if not price.is_finite() or price<=0 or price>Decimal('9999999999.99'):raise ValueError()
            if values['currency'] not in ('UAH','USD','EUR'):raise ValueError()
            qty=values['quantity']
            if qty and not re.fullmatch(r'\d{1,6}',qty):raise ValueError()
            if values['availability'] not in ('in_stock','out_of_stock','on_order','unknown'):raise ValueError()
            record=dict(source='partline',source_type='new_parts',source_article=number,manufacturer=brand,original_name=values['name'],price=str(price.quantize(Decimal('.01'))),currency=values['currency'],quantity=int(qty) if qty else None,availability=values['availability'],observed_at=None,request_status='fixture_only',synthetic=True,oem_confirmed=False,vehicle_compatibility='unverified')
            if number.casefold()!=article.casefold() or manufacturer and brand.casefold()!=manufacturer.casefold():continue
            key=json.dumps(record,sort_keys=True,separators=(',',':'))
            if key in seen:duplicates+=1;continue
            seen.add(key);offers.append(record)
        except (ValueError,TypeError,InvalidOperation):raise ProviderError('PARTLINE_INVALID_OFFER') from None
    return dict(source='partline',source_type='new_parts',mode='fixture',synthetic=True,live=False,adapter_version=VERSION,request_status='fixture_only' if offers else 'fixture_empty',observed_at=None,external_requests=0,query_article=article,query_manufacturer=manufacturer,offers_found=len(offers),duplicates=duplicates,offers=offers,request_completed=False,recommendation_eligible=False,committed=False)


def run_fixture(article,manufacturer,checksum,progress):
    progress(0,None,'fixture')
    raw,actual=fixture_bytes()
    if actual!=checksum:raise ProviderError('PARTLINE_FIXTURE_CHANGED')
    deadline=time.monotonic()+TIMEOUT_SECONDS
    def bounded(current,total,phase):
        if time.monotonic()>=deadline:raise ProviderError('PARTLINE_TIMEOUT')
        progress(current,total,phase)
    result=parse_fixture(TestResponse(raw),article,manufacturer,bounded)
    if time.monotonic()>=deadline:raise ProviderError('PARTLINE_TIMEOUT')
    result['fixture_sha256']=actual
    artifact=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    if len(artifact)>MAX_BYTES:raise ProviderError('PARTLINE_RESPONSE_LIMIT')
    return result,artifact
