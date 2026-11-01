"""Normalize VIN descriptions without changing OEM codes or inventing specifications."""
import re

def clean(value):
    if value is None:return ""
    return str(value).strip()

def ukrainian(key,value):
    raw=clean(value)
    if not raw:return ""
    low=raw.casefold()
    if key=="drive_type":
        if low in ("fwd","front-wheel drive","front wheel drive","front wheel drive (fwd)") or low.startswith("front-wheel drive"):return "Передній (FWD)"
        if low in ("rwd","rear-wheel drive","rear wheel drive") or low.startswith("rear-wheel drive"):return "Задній (RWD)"
        if low in ("awd","all-wheel drive","all wheel drive"):return "Повний (AWD)"
        if low in ("4wd","four-wheel drive","four wheel drive","4x4"):return "Повний (4WD)"
    if key=="body_class":
        values={"wagon":"Універсал","station wagon":"Універсал","sedan":"Седан","hatchback":"Хетчбек","pickup":"Пікап","sport utility vehicle (suv)/multi-purpose vehicle (mpv)":"Позашляховик / SUV","suv":"Позашляховик (SUV)","coupe":"Купе","convertible":"Кабріолет","minivan":"Мінівен","van":"Фургон"}
        return values.get(low,raw)
    if key=="fuel_type":
        values={"diesel":"Дизель","gasoline":"Бензин","petrol":"Бензин","electric":"Електро","hybrid":"Гібрид"}
        return values.get(low,raw)
    if key=="transmission":
        match=re.fullmatch(r"(\d+)[- ]speed\s+(automatic|manual)",low)
        if match:
            return f"{match.group(1)}-ступенева "+("автоматична" if match.group(2)=="automatic" else "механічна")
        if low in ("automatic","automatic transmission"):return "Автоматична"
        if low in ("manual","manual transmission"):return "Механічна"
        if re.fullmatch(r"\d+mt",low):return raw[:-2]+"-ступенева механічна"
        if re.fullmatch(r"\d+at",low):return raw[:-2]+"-ступенева автоматична"
    if key=="plant_country":
        countries={"sweden":"Швеція","germany":"Німеччина","united states (usa)":"США","united states":"США","mexico":"Мексика","japan":"Японія","south korea":"Південна Корея","china":"Китай","belgium":"Бельгія","united kingdom":"Велика Британія"}
        return countries.get(low,raw)
    return raw

def normalize(vehicle):
    return {key:(ukrainian(key,value) if value is not None else None) for key,value in vehicle.items()}

def merge_verified(existing,incoming):
    """Never overwrite a nonempty conflicting specification from another source."""
    merged=dict(existing)
    conflicts={}
    for key,value in incoming.items():
        if value in ("",None):continue
        value=ukrainian(key,value)
        prior=merged.get(key)
        if prior not in ("",None):
            if ukrainian(key,prior).casefold()!=str(value).casefold() and key not in ("trim","plant_country"):
                conflicts[key]={"primary":str(prior),"secondary":str(value)}
            continue
        merged[key]=value
    return merged,conflicts

def validate_consistency(vehicle):
    """Report suspicious cross-field values; never infer or overwrite engine data."""
    issues={}
    engine=clean(vehicle.get("engine"))
    size=vehicle.get("engine_displacement_l")
    if engine and size not in ("",None):
        match=re.search(r"(?<!\\d)(\\d{1,2}\\.\\d)\\s*[lл](?![a-z])",engine,re.I)
        if match:
            try:
                stated=float(size)
                described=float(match.group(1))
                if abs(stated-described)>0.25:
                    issues["engine_displacement_l"]=(
                        f"Опис двигуна містить {described:g} л, але поле об’єму — {stated:g} л. "
                        "Перевірте модифікацію за VIN перед створенням авто."
                    )
            except (ValueError,TypeError):
                pass
    return issues
