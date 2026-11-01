"""Opt-in European VIN enrichment. No lookup or billing without explicit credentials."""
import hashlib
import json
import os
from urllib.request import Request, urlopen

LABELS={
 "Make":"manufacturer","Model":"model","Model Year":"year","Engine Model":"engine",
 "Engine Displacement (l)":"engine_displacement_l","Engine Displacement (ccm)":"engine_displacement_cc",
 "Fuel Type - Primary":"fuel_type","Transmission":"transmission","Transmission Type":"transmission",
 "Drive":"drive_type","Body":"body_class","Trim":"trim","Plant Country":"plant_country",
 "Engine Power (kW)":"engine_power_kw","Engine Cylinders":"engine_cylinders",
}
def europe_vin(vin):
    key=os.getenv("WAREHOUSE_VINCARIO_API_KEY","").strip()
    secret=os.getenv("WAREHOUSE_VINCARIO_SECRET_KEY","").strip()
    enabled=os.getenv("WAREHOUSE_VINCARIO_ENABLED","false").lower()=="true"
    if not (key and secret and enabled):
        return None
    checksum=hashlib.sha1(f"{vin}|decode|{key}|{secret}".encode()).hexdigest()[:10]
    url=f"https://api.vincario.com/3.2/{key}/{checksum}/decode/{vin}.json"
    with urlopen(Request(url,headers={"Accept":"application/json","User-Agent":"CarPotWarehouse/1.0"}),timeout=8) as response:
        document=json.loads(response.read(160000))
    if not isinstance(document,dict) or not isinstance(document.get("decode"),list):
        raise ValueError("VIN provider returned unexpected data")
    raw={str(row.get("label")):row.get("value") for row in document["decode"] if isinstance(row,dict)}
    mapped={}
    for label,key_name in LABELS.items():
        value=raw.get(label)
        if value not in (None,"","null","N/A"):
            mapped[key_name]=str(value).strip()
    if mapped.get("year"):
        y=mapped["year"]
        mapped["year"]=int(y) if y.isdigit() and 1886<=int(y)<=2100 else None
    fuel=mapped.get("fuel_type","").lower()
    if "diesel" in fuel:mapped["fuel_type"]="Дизель"
    elif "gasoline" in fuel or "petrol" in fuel:mapped["fuel_type"]="Бензин"
    # Never present a disembodied year without a matched model.
    if not mapped.get("model"):mapped.pop("year",None)
    return mapped if mapped.get("manufacturer") and mapped.get("model") else None
