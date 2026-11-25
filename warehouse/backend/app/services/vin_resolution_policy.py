"""Comparison of explicitly sourced VIN and catalogue attributes."""
import re
import unicodedata
from math import isfinite

from app.services.vin_normalize import drive_code

ALIASES = {
    "vehicle_type": {
        "passenger": ("passenger car", "passenger", "легковий автомобіль",),
        "commercial": ("commercial vehicle", "commercial", "heavy truck", "truck tractor", "вантажний автомобіль", "автобус", "bus", "tractor truck"),
    },
    "body_class": {
        "sedan": ("sedan", "saloon", "седан", "стандартний седан"),
        "wagon": ("station wagon", "wagon", "estate", "універсал"),
        "hatchback": ("hatchback", "хетчбек", "хетчбек/ліфтбек"),
        "suv": ("suv", "sport utility vehicle (suv)", "позашляховик (suv)", "позашляховик"),
        "coupe": ("coupe", "coupé", "купе"),
        "convertible": ("convertible", "cabriolet", "кабріолет"),
        "van": ("van", "фургон", "box van"),
        "minivan": ("minivan", "мінівен"),
        "pickup": ("pickup", "пікап"),
        "tractor": ("tractor unit", "truck tractor", "сідельний тягач"),
    },
    "fuel_type": {
        "diesel": ("diesel", "дизель", "дизельне паливо"),
        "petrol": ("petrol", "gasoline", "benzin", "бензин"),
        "electric": ("electric", "electric motor", "електро", "електричний"),
        "hybrid": ("hybrid", "гібрид", "petrol/electric", "бензин/електро"),
        "lpg": ("lpg", "liquefied petroleum gas", "зріджений газ"),
        "cng": ("cng", "compressed natural gas", "природний газ"),
        "hydrogen": ("hydrogen", "водень"),
    },
    "transmission": {
        "manual": ("manual", "manual transmission", "механічна кпп", "механічна", "механічна коробка передач", "mt"),
        "automatic": ("automatic", "automatic transmission", "автоматична кпп", "автоматична", "автоматична коробка передач", "at", "cvt", "dct", "amt", "варіатор (cvt)", "роботизована кпп (amt)", "кпп із подвійним зчепленням (dct)"),
    },
}
ATTRIBUTE_NAMES = {
    "generation": ("generation", "platform", "покоління"),
    "body_class": ("body type", "body class", "body construction type", "construction type", "тип кузова", "кузов"),
    "fuel_type": ("fuel type", "fuel", "тип палива", "вид палива", "паливо"),
    "engine_code": ("engine code", "engine number", "motor code", "код двигуна"),
    "engine_displacement_l": ("capacity (cc)", "capacity (ccm)", "engine capacity", "engine displacement", "displacement", "cylinder capacity", "engine displacement (cc)", "engine displacement (l)", "displacement (cc)", "displacement (ccm)", "displacement (l)", "об'єм двигуна", "робочий об'єм (см³)"),
    "engine_power_kw": ("power (kw)", "power kw", "engine power (kw)", "engine power", "потужність (квт)"),
    "engine_power_hp": ("power (hp)", "power (ps)", "engine power (hp)", "horsepower", "потужність (к.с.)"),
    "transmission": ("transmission", "transmission type", "gearbox type", "gearbox", "тип коробки передач", "кпп"),
    "drive_type": ("drive type", "drive", "drivetrain", "traction type", "тип приводу", "привід"),
    "transmission_speeds": ("number of gears", "gears", "transmission speeds", "кількість передач"),
    "doors": ("doors", "number of doors", "кількість дверей"),
    "engine_cylinders": ("cylinders", "number of cylinders", "кількість циліндрів"),
}
TECHNICAL = tuple(key for key in ATTRIBUTE_NAMES if key != "engine_power_hp")
FIELDS = ("manufacturer", "model", "year", "vehicle_type", "engine", *TECHNICAL, "engine_power_hp")
QUESTIONS = ("vehicle_type", "model", "generation", "year", "body_class", "fuel_type",
             "engine_code", "engine_displacement_l", "engine_power_kw", "transmission",
             "drive_type", "transmission_speeds", "doors", "engine_cylinders")


def key(value):
    return "".join(char for char in unicodedata.normalize("NFKD", str(value or "")).casefold()
                   if char.isalnum())


def number(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([A-Za-zА-Яа-яІіЇїЄє.\s0-9]*)", text)
    if not match:
        return None, ""
    result = float(match[1].replace(",", "."))
    return (result, key(match[2])) if isfinite(result) and result > 0 else (None, "")


def normalized(field, value):
    name = key(value)
    if name in {"", "unknown", "none", "null", "na", "notapplicable", "невідомо", "неуточнено", "невизначено"}:
        return None
    if field == "manufacturer":
        from app.services.vin_source_directory import maker_key
        return maker_key(str(value))
    if field in ALIASES:
        if field == "transmission":
            name = re.sub(r"^(?:\d+speed|\d+ступенева)", "", name)
            name = re.sub(r"^\d+(?=[am]t$)", "", name)
        return _ALIASES[field].get(name)
    if field == "generation":
        return _ROMAN.get(name, name)
    if field == "drive_type":
        return drive_code(value) or _DRIVE.get(name)
    if field in {"year", "engine_displacement_l", "engine_power_kw", "engine_power_hp",
                 "transmission_speeds", "doors", "engine_cylinders"}:
        amount, unit = number(value)
        if amount is None:
            return None
        if field == "engine_displacement_l":
            if unit in {"cc", "ccm", "cm3", "см3"} or not unit and amount >= 100:
                amount /= 1000
            return amount if 0 < amount <= 99.9 and unit in {"", "cc", "ccm", "cm3", "см3", "l", "л", "liter", "litre"} else None
        if field in {"engine_power_kw", "engine_power_hp"}:
            if unit in {"hp", "bhp"} or not unit and field == "engine_power_hp":
                return round(amount * 0.7457, 3)
            if unit in {"ps", "cv", "кс"}:
                return round(amount * 0.7355, 3)
            return amount if unit in {"", "kw", "квт"} else None
        if unit or not amount.is_integer():
            return None
        return int(amount) if field != "year" or 1886 <= amount <= 2100 else None
    if field == "engine_code" and not re.fullmatch(r"[\w .-]{2,40}", str(value), re.UNICODE):
        return None
    return name


_ALIASES = {field: {key(alias): canonical for canonical, values in groups.items() for alias in values}
            for field, groups in ALIASES.items()}
_DRIVE = {"front": "FWD", "rear": "RWD", "передній": "FWD", "задній": "RWD",
          "переднійпривід": "FWD", "заднійпривід": "RWD"}
_ATTRIBUTES = {key(alias): field for field, values in ATTRIBUTE_NAMES.items() for alias in values}
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
_SERIES = re.compile(r"(?:(\d+)\s*(?:series|серія|er)|(?:series|серія)\s*(\d+))\b", re.I)


def model_parts(value):
    text = str(value or "").strip().casefold()
    parenthetical = re.findall(r"\(([^()]*)\)", text)
    label = re.sub(r"\([^()]*\)", "", text).strip()
    series = _SERIES.fullmatch(label)
    if series or label.isdecimal():
        name = next(filter(None, series.groups())) if series else label
        return name, {key(part) for group in parenthetical for part in re.split(r"[/,]", group)}, ("", name)
    prefix, _, tail = label.rpartition(" ")
    generations = {key(part) for group in parenthetical for part in re.split(r"[/,]", group)}
    if prefix and tail in _ROMAN:
        label = prefix
        generations.add(_ROMAN[tail])
    identifier = re.fullmatch(r"([a-z]+)[ -]?(\d+)", label)
    return key(label), generations, identifier.groups() if identifier else None


def model_relation(left, right):
    a, a_generations, a_id = model_parts(left)
    b, b_generations, b_id = model_parts(right)
    if a and a == b:
        if a_generations and b_generations and a_generations.isdisjoint(b_generations):
            a_ordinal = str(left).casefold().split()
            b_ordinal = str(right).casefold().split()
            if a_ordinal[-1] in _ROMAN and b_ordinal[-1] in _ROMAN:
                return "mismatch"
            if all(_platform_relation(value, b_generations) == "mismatch" for value in a_generations):
                return "mismatch"
        return "compatible"
    if a_id and b_id and a_id[0] == b_id[0] and a_id[1] != b_id[1]:
        return "mismatch"
    return "unknown"


def interval(value):
    text = str(value or "").strip()
    # Oracle intervals can contain month/year or a compact YYYYMM value.
    parts = re.fullmatch(
        r"((?:(?:0?[1-9]|1[0-2])[./-])?\d{4}(?:[./]?(?:0[1-9]|1[0-2]))?)?\s*[-–—]\s*"
        r"((?:(?:0?[1-9]|1[0-2])[./-])?\d{4}(?:[./]?(?:0[1-9]|1[0-2]))?)?", text)
    if not parts:
        return None, None
    years = []
    for part in parts.groups():
        match = re.search(r"(?<!\d)(18\d{2}|19\d{2}|20\d{2}|2100)(?:[./]?[01]\d)?$", part or "")
        years.append(int(match[1]) if match else None)
    start, end = years
    return (None, None) if start and end and end < start else (start, end)


def year_relation(year, period):
    start, end = period
    if year is None or not (start or end):
        return "unknown"
    # A model year can label production in the previous calendar year.
    if (start and year < start - 1) or (end and year > end + 1):
        return "mismatch"
    if (start and year < start) or (end and year > end):
        return "unknown"
    return "compatible"


def source_specs(rows):
    """Unmapped keys and conflicting source values cannot prove a mismatch."""
    values = {}
    for row in rows:
        attribute = row.get("attribute_type", row.get("attributetype"))
        field = _ATTRIBUTES.get(key(attribute))
        if field:
            raw = row.get("display_value", row.get("displayvalue"))
            value = normalized(field, raw)
            if field == "engine_power_hp":
                if key(attribute) == "powerps" and number(raw)[1] == "" and value is not None:
                    value *= 0.7355 / 0.7457
                field = "engine_power_kw"
            if value is not None:
                label = f"{value:g} kW" if field == "engine_power_kw" else raw
                values.setdefault(field, {}).setdefault(value, label)
    return {field: observations for field, observations in values.items() if len(observations) == 1}


def equivalent(field, left, right):
    if field == "engine_displacement_l":
        return abs(left - right) <= 0.05
    if field == "engine_power_kw":
        return abs(left - right) <= 2
    if field == "drive_type" and {left, right} == {"AWD", "4WD"}:
        return True
    return left == right


def _displacement_precision(raw):
    amount, unit = number(raw)
    if unit in {"cc", "ccm", "cm3", "см3"} or not unit and amount and amount >= 100:
        return 0.001
    match = re.match(r"\d+[.,](\d+)", str(raw).strip())
    return 10 ** -len(match[1]) if match else 0.1


def _observations_match(field, value, reported, item, source):
    if field == "engine_displacement_l" and reported:
        precision = max(_displacement_precision(reported), _displacement_precision(source))
        return abs(value - item) <= max(0.001, precision / 2) + 1e-9
    return equivalent(field, value, item)


def _platform_relation(generation, identifiers):
    if generation in identifiers:
        return "compatible"
    code = re.fullmatch(r"([a-z]+)\d+", generation)
    if code and identifiers and all(re.fullmatch(code[1] + r"\d+", item) for item in identifiers):
        return "mismatch"
    return "unknown"


def compare(evidence, candidate):
    facts = {}
    for field, observation in evidence.items():
        value = observation["value"]
        if value is None:
            continue
        if field == "model":
            facts[field] = model_relation(value, candidate["model"])
        elif field == "year":
            relations = [year_relation(value, candidate[k]) for k in ("model_period", "variant_period")]
            facts[field] = ("mismatch" if "mismatch" in relations else
                            "compatible" if "compatible" in relations else "unknown")
        else:
            possibilities = candidate["specs"].get(field, {})
            if field == "generation" and not possibilities:
                _, identifiers, _ = model_parts(candidate["model"])
                facts[field] = _platform_relation(value, identifiers)
            elif field == "fuel_type" and possibilities and (
                    value == "hybrid" or "hybrid" in possibilities) and value not in possibilities:
                facts[field] = "unknown"
            elif possibilities:
                matches = any(_observations_match(field, value, observation.get("reported"), item, source)
                              for item, source in possibilities.items())
                if field == "generation" and not matches:
                    matches = None if not all(value.isdecimal() == item.isdecimal() for item in possibilities) else False
                facts[field] = "unknown" if matches is None else "compatible" if matches else "mismatch"
            else:
                facts[field] = "unknown"
    return facts


def needed_questions(evidence, candidates, answered):
    questions = []
    for field in QUESTIONS:
        if field in answered or evidence.get(field, {}).get("value") is not None:
            continue
        values = {}
        for candidate in candidates:
            if field == "model":
                values.setdefault(model_parts(candidate["model"])[0], candidate["model"])
            else:
                for value, label in candidate["specs"].get(field, {}).items():
                    if not any(equivalent(field, value, prior) for prior in values):
                        values[value] = label
        if field == "year":
            periods = {candidate["variant_period"] if any(candidate["variant_period"]) else candidate["model_period"]
                       for candidate in candidates}
            if len({period for period in periods if any(period)}) > 1:
                questions.append(dict(field=field, options=[]))
        elif len(values) > 1 and field != "model":
            questions.append(dict(field=field, options=list(map(str, values.values()))))
    return questions
