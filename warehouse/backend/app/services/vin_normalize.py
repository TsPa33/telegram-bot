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
        code=drive_code(raw)
        return {'FWD':'Передній привід (FWD)','RWD':'Задній привід (RWD)','AWD':'Повний привід (AWD)','4WD':'Повний привід (4WD)'}.get(code,raw)
    if key=="body_class":
        values={"wagon":"Універсал","station wagon":"Універсал","sedan":"Седан","hatchback":"Хетчбек","pickup":"Пікап","sport utility vehicle (suv)/multi-purpose vehicle (mpv)":"Позашляховик (SUV) / MPV","sport utility vehicle (suv)":"Позашляховик (SUV)","suv":"Позашляховик (SUV)","coupe":"Купе","convertible":"Кабріолет","minivan":"Мінівен","van":"Фургон"}
        return values.get(low,raw)
    if key in ("fuel_type","fuel_secondary"):
        values={"diesel":"Дизель","gasoline":"Бензин","petrol":"Бензин","electric":"Електро","hybrid":"Гібрид"}
        return values.get(low,raw)
    if key=="transmission":
        match=re.fullmatch(r"(\d+)[- ]speed\s+(automatic|manual)",low)
        if match:
            return f"{match.group(1)}-ступенева "+("автоматична" if match.group(2)=="automatic" else "механічна")
        if low in ("automatic","automatic transmission"):return "Автоматична КПП"
        if low in ("manual","manual transmission"):return "Механічна КПП"
        if re.fullmatch(r"\d+mt",low):return raw[:-2]+"-ступенева механічна"
        if re.fullmatch(r"\d+at",low):return raw[:-2]+"-ступенева автоматична"
    if key=="electrification":
        return {"mild hev (hybrid electric vehicle)":"М’який гібрид (MHEV)","hev (hybrid electric vehicle) - level unknown":"Гібрид (HEV)","phev (plug-in hybrid electric vehicle)":"Плагін-гібрид (PHEV)","bev (battery electric vehicle)":"Електромобіль (BEV)","not electrified":"Без електрифікації"}.get(low,raw)
    if key=="engine_configuration":
        return {"in-line":"Рядний","v-shaped":"V-подібний","horizontally opposed (boxer)":"Опозитний"}.get(low,raw)
    if key in ("turbo","abs"):
        return {"yes":"Так","no":"Ні","standard":"Стандартно","optional":"Опція"}.get(low,raw)
    if key=="steering_location":
        return {"left-hand drive (lhd)":"Ліве кермо (LHD)","right-hand drive (rhd)":"Праве кермо (RHD)"}.get(low,raw)
    if key=="transmission":
        return {"continuously variable transmission (cvt)":"Варіатор (CVT)","automated manual transmission (amt)":"Роботизована КПП (AMT)","dual-clutch transmission (dct)":"КПП із подвійним зчепленням (DCT)"}.get(low,raw)
    shared={
      'brake_system':{'hydraulic':'Гідравлічна','air':'Пневматична'},
      'cooling':{'water':'Рідинне','air':'Повітряне'},
      'wheelbase_type':{'long':'Довга','short':'Коротка'},
      'tpms':{'direct':'Прямий контроль (TPMS)','indirect':'Непрямий контроль (TPMS)'},
      'valve_train':{'dual overhead cam (dohc)':'Два верхні розподільні вали (DOHC)','single overhead cam (sohc)':'Один верхній розподільний вал (SOHC)'},
      'battery_type':{'lithium-ion/li-ion':'Літій-іонний','lithium-ion':'Літій-іонний'},
      'vehicle_type':{'passenger car':'Легковий автомобіль','multipurpose passenger vehicle (mpv)':'Багатоцільовий пасажирський автомобіль (MPV)'},
      'fuel_injection':{'multipoint fuel injection (mpfi)':'Багатоточкове впорскування (MPFI)','direct fuel injection':'Безпосереднє впорскування'},
    }
    if key in shared:return shared[key].get(low,raw)
    if key=="plant_country":
        countries={"sweden":"Швеція","germany":"Німеччина","united states (usa)":"США","united states":"США","mexico":"Мексика","japan":"Японія","south korea":"Південна Корея","china":"Китай","belgium":"Бельгія","united kingdom":"Велика Британія"}
        return countries.get(low,raw)
    return raw

def drive_code(value):
    """Shared storage mapping; never infer drive from a model or trim."""
    raw=clean(value).upper()
    match=re.search(r'\b(FWD|RWD|AWD|4WD)\b',raw)
    if match:return match.group(1)
    raw=raw.replace('-',' ')
    for phrase,code in [('ALL WHEEL','AWD'),('FOUR WHEEL','4WD'),('4 WHEEL','4WD'),('FRONT WHEEL','FWD'),('REAR WHEEL','RWD')]:
        if phrase in raw:return code
    return ''


def normalize(vehicle):
    return {key:(ukrainian(key,value) if value is not None else None) for key,value in vehicle.items()}

def equivalent(key,left,right):
    if key in {'year','engine_displacement_l','engine_power_kw','engine_power_hp','engine_cylinders','doors','transmission_speeds'}:
        from decimal import Decimal,InvalidOperation
        try:return Decimal(str(left))==Decimal(str(right))
        except InvalidOperation:pass
    return ukrainian(key,left).casefold()==ukrainian(key,right).casefold()


def merge_verified(existing,incoming):
    """Never overwrite a nonempty conflicting specification from another source."""
    merged=dict(existing)
    conflicts={}
    for key,value in incoming.items():
        if value in ("",None):continue
        value=ukrainian(key,value)
        prior=merged.get(key)
        if prior not in ("",None):
            if not equivalent(key,prior,value):
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
        match=re.search(r"(?<!\d)(\d{1,2}\.\d)\s*[lл](?![a-z])",engine,re.I)
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
