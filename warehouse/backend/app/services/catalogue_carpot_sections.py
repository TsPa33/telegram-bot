"""CarPot's own 12-section navigation taxonomy, independent of source catalogues.

This classifier is advisory only. It does not infer OEM/VIN fitment, change stock,
or write canonical IDs. Ambiguous broad import classes require owner review.
"""
import re
from dataclasses import dataclass

SECTIONS = (
    "Двигун та його системи",
    "Трансмісія та привід",
    "Підвіска та ходова частина",
    "Кермове управління",
    "Гальмівна система",
    "Кузов та зовнішні деталі",
    "Салон та інтер’єр",
    "Електрика та електроніка",
    "Освітлення",
    "Кліматична система",
    "Системи безпеки",
    "Обладнання та витратні матеріали",
)

# Deliberately high-precision groups; overlapping or broad terms are reviewed.
_RULES = (
    (0, r"двигун|двигатель|мотор|паливн|топливн|свічк|свеч|запалюван|зажиган|ремен|ремінн"),
    (1, r"коробк.{0,8}передач|трансміс|трансмис|зчеплен|сцеплен|привід кол|привод кол|кардан"),
    (2, r"амортиз|пружин|підвіск|подвес|ходов|маточин|ступиц|шини|колеса|колёса"),
    (3, r"кермов|рулев|рульов|рейка"),
    (4, r"гальм|тормозн|супорт|колодк|abs"),
    (5, r"кузов|капот|бампер|крыло|крило|двер|замок|замки|дзеркал|зеркал"),
    (6, r"салон|інтер’єр|интерьер|сидін|сиден|обшив|оздоблен|отделк"),
    (7, r"електрик|электрик|проводк|стартер|генератор|електрон|электрон"),
    (8, r"освіт|освещ|фари|фара|ліхтар|фонар|оптик"),
    (9, r"кондиціон|кондиционер|опален|отоплен|вентиляц|клімат"),
    (10, r"безпек|безопас|подушк"),
    (11, r"обслугов|сервіс|детали для сервиса|комплектую|комплектующ|причіп|прицеп"),
)
_PATTERNS = tuple((index,re.compile(pattern,re.IGNORECASE)) for index,pattern in _RULES)
# Some terms span multiple categories, even if a single regex happens to match.
_BROAD = re.compile(r"силовий агрегат|підвіск.{0,35}кермов|подвес.{0,35}рулев|запалюван.{0,25}розжар|зажиган.{0,25}накал|навісні елементи",re.IGNORECASE)

def propose_section(category: str, subcategory: str, part_name: str) -> dict:
    """Suggest section only if unambiguous, with evidence and explicit review status."""
    values=[("subcategory",subcategory),("category",category),("part_name",part_name)]
    for origin,name in values:
        if not name or _BROAD.search(name):
            if name and _BROAD.search(name):
                return {"section":None,"status":"review_required","reason":"mixed_systems","evidence":origin}
            continue
        hits={i for i,pattern in _PATTERNS if pattern.search(name)}
        if len(hits)>1:
            return {"section":None,"status":"review_required","reason":"multiple_systems","evidence":origin}
        if len(hits)==1:
            i=next(iter(hits))
            return {"section":SECTIONS[i],"status":"suggested","reason":"rule_match","evidence":origin}
    return {"section":None,"status":"review_required","reason":"no_confident_match","evidence":None}
