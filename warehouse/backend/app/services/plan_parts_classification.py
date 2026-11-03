"""Conservative, vehicle-independent CarPot classification of plan.parts types.

Never use aftermarket offers, count, or a translated term to assert VIN
compatibility. A classification can only link to an existing owner's Category
row; unresolved names remain review_required rather than creating duplicates.
"""
import re
import unicodedata

from sqlalchemy import select

from app.models import Category
from app.services.catalogue_carpot_sections import SECTIONS, propose_subcategory


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value or "").casefold()).split())


# Only the existing CarPot twelve-section concept is used. Aliases here are
# synonyms for resolving preexisting user-owned Category rows, not new nodes.
CATEGORY_ALIASES = {
    "Двигун та його системи": ("двигун та його системи", "двигун", "двигун та навісне", "двигун і системи", "силовий агрегат"),
    "Трансмісія та привід": ("трансмісія та привід", "трансмісія", "трансмісія і привід"),
    "Підвіска та ходова частина": ("підвіска та ходова частина", "ходова частина", "підвіска", "підвіска та колеса"),
    "Кермове управління": ("кермове управління", "кермове керування", "рульове управління"),
    "Гальмівна система": ("гальмівна система", "гальма"),
    "Кузов та зовнішні деталі": ("кузов та зовнішні деталі", "кузов", "кузовні деталі"),
    "Салон та інтер’єр": ("салон та інтер’єр", "салон", "інтер'єр"),
    "Електрика та електроніка": ("електрика та електроніка", "електрика", "електрообладнання"),
    "Освітлення": ("освітлення", "світлотехніка", "оптика"),
    "Кліматична система": ("кліматична система", "клімат", "опалення і кондиціонування", "кондиціонування та опалення"),
    "Системи безпеки": ("системи безпеки", "безпека", "пасивна безпека"),
    "Обладнання та витратні матеріали": ("обладнання та витратні матеріали", "витратні матеріали", "обладнання та інструменти"),
}

# English source labels are stable when automatic Ukrainian translation varies.
# Patterns are intentionally narrow and ordered only for explicit overrides.
TOOL = re.compile(r"\b(?:tool|tools|toolbox|wrench|socket set|puller|installer set|workshop equipment)\b|інструмент|знімач|ключ для.*фільтр", re.I)
CONSUMABLE = re.compile(r"\b(?:oil(?! pump| cooler| seal| filter| pan| line)|antifreeze|fluid|additive|paste|cleaner|grease|sealant|lubricant|cleaning)\b|\b(?:рідина|олива|масло|антифриз|паста|мастил|очищувач|добавка)\b",re.I)
KIT = re.compile(r"\b(?:kit|set|assembly kit)\b|комплект|набір",re.I)

# Specific names first; no catch-all "sensor", "gasket", "valve" that
# would incorrectly classify a different vehicle subsystem.
_RULES = {
    "Гальмівна система": r"brake|caliper|гальм|супорт|колодк",
    "Кермове управління": r"steering|tie rod|кермов|рульов|керма",
    "Освітлення": r"headlight|bulb|fog light|rear light|tail light|direction indicator|stop light|reflector|світл|лампоч|ліхтар|фара|поворотник|відбивач|освітлен",
    "Кліматична система": r"air conditioning|a/c compressor|interior blower|cabin blower|heater|evaporator|condenser|клімат|кондиціон|обігрів|пічк|вентилятор салону",
    "Трансмісія та привід": r"drive shaft|driveshaft|transmission|gearbox|differential|prop shaft|propshaft|clutch(?!.*compressor)|привідн.{0,10}вал|коробк.{0,10}передач|диференціал|шрус|зчеплен|кардан",
    "Підвіска та ходова частина": r"suspension|shock absorber|strut|stabiliser|stabilizer|ball joint|axle beam|wheel bearing|підвіск|амортиз|стабілізатор|кульова опора|маточин|пружин",
    "Системи безпеки": r"airbag|seat belt|подушк.{0,10}безпек|ремен.{0,10}безпек",
    "Кузов та зовнішні деталі": r"bonnet|hood|bumper|wing|fender|tailgate|door lock|door check|door handle|window regulator|mirror|quarter panel|grille|капот|бампер|крил|дзеркал|замок двер|двер|решітк.{0,10}радіатор|склопідіймач",
    "Електрика та електроніка": r"alternator|starter|battery|fuse|relay|control unit|wiring|parking sensor|генератор|стартер|акумулятор|запобіжник|реле|блок керування|датчик тиску повітря.*висот",
    "Салон та інтер’єр": r"interior light|seat cover|dashboard|floor mat|boot liner|cargo area|interior trim|салон|сидін|панель приладів|килимок",
    "Двигун та його системи": r"engine|fuel|oil filter|air filter|cabin air filter|camshaft|crankshaft|cylinder|coolant|radiator|turbocharger|timing belt|intake|exhaust|injection|spark plug|water pump|vacuum pump|палив|масляний фільтр|повітряний фільтр|розподільн.{0,10}вал|колінчаст|радіатор охолодж|охолоджувальн|турбін|двигун|впускн|випускн|форсунк|водяний насос",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in _RULES.items()}

# Context-sensitive overrides for terms shared by two systems.
_OVERRIDES = (
    (re.compile(r"brake.*(?:light|bulb)|(?:стоп сигнал|стоп-сигнал)", re.I), "Освітлення"),
    (re.compile(r"brake.*(?:pressure sensor|switch)", re.I), "Гальмівна система"),
    (re.compile(r"(?:oil cooler.*transmission|transmission.*oil cooler|прокладка.*коробк)", re.I), "Трансмісія та привід"),
    (re.compile(r"(?:coolant.*(?:tank|radiator|hose)|радіатор охолодж|охолоджувальн)", re.I), "Двигун та його системи"),
    (re.compile(r"(?:brake.*sensor|sensor.*brake|датчик.*гальм)", re.I), "Гальмівна система"),
    (re.compile(r"(?:sensor.*(?:fuel|engine|camshaft|crankshaft)|датчик.*(?:колінчаст|розподільн|палив))", re.I), "Двигун та його системи"),
    (re.compile(r"(?:air conditioning.*(?:actuator|valve)|привід заслінки системи кондиціон)", re.I), "Кліматична система"),
    (re.compile(r"(?:gasket.*(?:differential|gearbox|transmission)|ущільнювач.*диференціал)", re.I), "Трансмісія та привід"),
    (re.compile(r"(?:gasket.*(?:fuel|camshaft|engine|crankcase|oil|cylinder|turbocharger)|ущільнювач.*(?:палив|розподільн|наддув))", re.I), "Двигун та його системи"),
    (re.compile(r"(?:bulb|лампочк|лампа|ліхтар)", re.I), "Освітлення"),
)

def classify(name_en: str, name_uk: str = "") -> dict:
    en = (name_en or "").strip()
    uk = (name_uk or "").strip()
    source = en or uk
    kind = "tool" if TOOL.search(source) else "consumable" if CONSUMABLE.search(source) else "kit" if KIT.search(source) else "part"
    # No verified parts classification may be inferred from vague descriptions.
    for regex, section in _OVERRIDES:
        if regex.search(source):
            return {"kind": kind, "section": section, "confidence": "rule", "reason": "explicit_context"}
    matches = {section for section, regex in _COMPILED.items() if regex.search(source)}
    if len(matches) != 1:
        # For manually entered labels, translated text can provide a second clue.
        if len(matches) == 0 and uk:
            matches = {section for section, regex in _COMPILED.items() if regex.search(uk)}
    return {"kind": kind, "section": next(iter(matches)) if len(matches) == 1 else None,
            "confidence": "rule" if len(matches) == 1 else "review",
            "reason": "single_system" if len(matches) == 1 else "ambiguous_or_unknown"}


def match_existing_category(db, account_id: str, classification: dict, name: str) -> dict:
    """Resolve existing category IDs; never invent nodes or pick ambiguous labels."""
    section = classification["section"]
    if not section:
        return {**classification, "category_id": None, "subcategory_id": None,
                "mapping": "review_required"}
    rows = list(db.scalars(select(Category).where(
        Category.account_id == account_id, Category.archived.is_(False)
    )))
    aliases = {normalize(x) for x in CATEGORY_ALIASES.get(section, ())}
    aliases.add(normalize(section))
    roots = [r for r in rows if r.parent_id is None and r.kind == "category" and normalize(r.name) in aliases]
    if len(roots) != 1:
        return {**classification, "category_id": None, "subcategory_id": None,
                "mapping": "review_required" if roots else "category_missing",
                "reason": "ambiguous_category" if roots else "category_not_in_workspace"}
    category = roots[0]
    proposal = propose_subcategory(section, "", "", name)
    children = [r for r in rows if r.parent_id == category.id and r.kind == "subcategory"]
    selected = [r for r in children if proposal["status"] == "suggested" and normalize(r.name) == normalize(proposal["subcategory"])]
    return {**classification, "category_id": category.id,
            "subcategory_id": selected[0].id if len(selected) == 1 else None,
            "mapping": "category_matched" if len(selected) != 1 else "subcategory_matched"}
