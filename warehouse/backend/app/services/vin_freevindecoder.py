"""Conservative on-demand public VIN page adapter. No bypass of site restrictions."""
from html.parser import HTMLParser
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from urllib.error import HTTPError, URLError
from threading import Lock
from time import monotonic
import re

AGENT="CarPotWarehouse/1.0 (+VIN lookup; respects robots.txt)"
BASE="https://www.freevindecoder.eu"
_cache={}
_guard=Lock()
_status={}
_policy=None
_policy_expires=0
_last_request=0.0
class Cells(HTMLParser):
    def __init__(self):
        super().__init__();self.capture=False;self.buf=[];self.rows=[];self.current=[];self.in_row=False
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.current=[];self.in_row=True
        if self.in_row and tag in ("th","td"):self.capture=True;self.buf=[]
    def handle_data(self,data):
        if self.capture:self.buf.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.capture:
            self.current.append(" ".join("".join(self.buf).split()));self.capture=False
        if tag=="tr" and self.in_row:
            if len(self.current)>=2:self.rows.append(self.current[:2])
            self.in_row=False

def extract_page(html,vin):
    """Only explicit table labels; never infer engine code, year or market."""
    cells=Cells();cells.feed(html)
    values={k.strip().casefold():v.strip() for k,v in cells.rows if k and v}
    def val(*keys):return next((values[k.casefold()] for k in keys if values.get(k.casefold())), '')
    if val('VIN','VIN-код') and val('VIN','VIN-код').upper()!=vin:return {}
    mapping={
      'manufacturer':('Зробіть','Make','Марка'), 'model':('Модель','Model'),
      'year':('Модель року','Model Year'), 'generation':('Generation','Покоління'),
      'series':('Series','Серія'), 'engine':('Тип двигуна','Engine Type','Engine Model'),
      'engine_code':('Engine Code','Код двигуна'), 'fuel_type':('Тип палива','Fuel Type'),
      'fuel_secondary':('Secondary Fuel Type','Додаткове паливо'),
      'transmission':('Передача','Transmission'), 'transmission_code':('Transmission Code','Код КПП'),
      'transmission_speeds':('Transmission Speeds','Gears'), 'drive_type':('Лінія руху','Drive Line'),
      'body_class':('Статура','Body Style'), 'engine_power_kw':('Двигун KiloWatts','Engine KiloWatts'),
      'engine_power_hp':('Engine Horsepower',), 'engine_cylinders':('Циліндри двигуна','Engine Cylinders'),
      'trim':('Рівень обрізки','Trim'), 'plant_country':('Виробляється в','Made In'),
      'plant_city':('Plant City',), 'market':('Market','Ринок'), 'doors':('Doors','Кількість дверей'),
      'electrification':('Electrification Level','Hybrid Type'),
    }
    result={key:val(*labels) for key,labels in mapping.items() if val(*labels)}
    if not result.get('manufacturer') or not result.get('model'):return {}
    year=result.get('year','')
    if year.isdigit() and 1886<=int(year)<=2100:result['year']=int(year)
    else:result.pop('year',None)
    cc=val('Зсув СІ','Displacement (ccm)')
    try:
        if 100<=float(cc.replace(',','.'))<=12000:result['engine_displacement_l']=round(float(cc.replace(',','.'))/1000,3)
    except ValueError:pass
    from app.services.vin_fields import EXTRA,present
    extra={}
    for source_key,(key,label) in EXTRA.items():
        value=val(source_key,re.sub(r'(?<=[a-z])(?=[A-Z])',' ',source_key))
        if present(value) and len(value)<=200:extra[key]={'label':label,'value':value,'source':'FreeVINDecoder'}
    if extra:result['additional']=extra
    return result


def source_status(vin):
    with _guard:return _status.get(vin,'no_data_or_access_unavailable')


def decode_page(vin):
    global _policy,_policy_expires,_last_request
    if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',vin):return None
    with _guard:
        entry=_cache.get(vin)
        if entry and entry[0]>monotonic():return dict(entry[1]) if entry[1] else None
    address=BASE+'/uk/'+quote(vin)
    status='unavailable_or_blocked';result=None
    try:
        with _guard:
            if _policy_expires<=monotonic():
                robots=RobotFileParser();robots.set_url(BASE+'/robots.txt')
                _policy=None;_policy_expires=monotonic()+30;status='policy_unavailable'
                with urlopen(Request(BASE+'/robots.txt',headers={'User-Agent':AGENT}),timeout=4) as policy:
                    raw_policy=policy.read(65537)
                    if len(raw_policy)<=65536 and policy.status==200:
                        robots.parse(raw_policy.decode('utf-8','replace').splitlines());_policy=robots;_policy_expires=monotonic()+300
            robots=_policy
        if robots is None:status='policy_unavailable'
        elif not robots.can_fetch(AGENT,address):status='robots_denied'
        else:
            delay=robots.crawl_delay(AGENT) or 1
            with _guard:
                allowed=monotonic()-_last_request>=delay
                if allowed:_last_request=monotonic()
            if not allowed:status='rate_limited'
            else:
                status='page_unavailable'
                with urlopen(Request(address,headers={'User-Agent':AGENT,'Accept':'text/html'}),timeout=7) as response:
                    raw=response.read(350001)
                    if response.status==200 and 'text/html' in response.headers.get('Content-Type','') and len(raw)<=350000:
                        result=extract_page(raw.decode('utf-8','replace'),vin) or None
                        status='reported' if result else 'no_explicit_vehicle_data'
    except (HTTPError,URLError,TimeoutError,OSError,ValueError):pass
    with _guard:
        if len(_cache)>=128:
            oldest=next(iter(_cache));_cache.pop(oldest);_status.pop(oldest,None)
        _cache[vin]=(monotonic()+(300 if result else 30),result)
        _status[vin]=status
    return dict(result) if result else None
