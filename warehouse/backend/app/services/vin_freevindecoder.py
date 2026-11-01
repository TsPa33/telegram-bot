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

def decode_page(vin):
    if not re.fullmatch("[A-HJ-NPR-Z0-9]{17}",vin):return None
    with _guard:
        entry=_cache.get(vin)
        if entry and entry[0]>monotonic():return dict(entry[1])
    address=BASE+"/uk/"+quote(vin)
    robots=RobotFileParser()
    try:
        robots.set_url(BASE+"/robots.txt")
        robots.read()
        # A missing or inaccessible robots policy must never be interpreted as consent.
        if not robots.can_fetch(AGENT,address):return None
        with urlopen(Request(address,headers={"User-Agent":AGENT,"Accept":"text/html"}),timeout=7) as response:
            if response.status!=200 or "text/html" not in response.headers.get("Content-Type",""):return None
            html=response.read(350000).decode("utf-8","replace")
    except (HTTPError,URLError,TimeoutError,OSError):
        return None
    cells=Cells()
    cells.feed(html)
    values={k.strip().casefold():v.strip() for k,v in cells.rows if k and v}
    def val(*keys):
        return next((values[k.casefold()] for k in keys if values.get(k.casefold())), "")
    make=val("Зробіть","Make","Марка")
    model=val("Модель","Model")
    year=val("Модель року","Model Year")
    if not (make and model and year.isdigit() and 1886<=int(year)<=2100):return None
    fuel=val("Тип палива","Fuel Type")
    engine=val("Тип двигуна","Engine Type")
    transmission=val("Передача","Transmission")
    drive=val("Лінія руху","Drive Line")
    cc=val("Зсув СІ","Displacement (ccm)")
    result={"manufacturer":make,"model":model,"year":int(year),
        "engine":engine,"fuel_type":"Дизель" if "diesel" in fuel.lower() else "Бензин" if "gasoline" in fuel.lower() else "",
        "transmission":transmission,"drive_type":drive,
        "body_class":val("Статура","Body Style"),
        "engine_power_kw":val("Двигун KiloWatts","Engine KiloWatts"),
        "engine_cylinders":val("Циліндри двигуна","Engine Cylinders"),
        "trim":val("Рівень обрізки","Trim"),
        "plant_country":val("Виробляється в","Made In")}
    if cc.isdigit() and int(cc)>0:result["engine_displacement_l"]=round(int(cc)/1000,3)
    with _guard:_cache[vin]=(monotonic()+3600,result)
    return dict(result)
