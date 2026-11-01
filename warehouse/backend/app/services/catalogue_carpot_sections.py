"""CarPot's own 12-section navigation taxonomy, independent of source catalogues.

This classifier is advisory only. It does not infer OEM/VIN fitment, change stock,
or write canonical IDs. Ambiguous broad import classes require owner review.
"""
import re

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


# CarPot-owned navigation taxonomy: subgroups are stable labels, not source IDs.
# Each tuple contains a subsection name and high-specificity technical terms.
SUBCATEGORIES = (
 (("Деталі двигуна",r"блок циліндр|головк.{0,10}блок|порш|колінвал|коленвал|розподільн.{0,10}вал|распредвал"),
  ("Паливна система",r"палив|топлив|форсунк|інжектор|инжектор"),
  ("Система запалювання",r"запалюван|зажиган|свічк|свеч|розжар|накал"),
  ("Система охолодження",r"охолодж|охлажд|радіатор двигун|радиатор двигателя|термостат"),
  ("Ремінний привід",r"ремінн|ремен|натяжн.{0,10}ролик"),
  ("Впускна та випускна системи",r"впуск|выпуск|випуск|выхлоп|турбін|турбин")),
 (("Коробка передач",r"коробк.{0,8}передач|кпп|акпп"),
  ("Зчеплення",r"зчеплен|сцеплен|вижимн"),
  ("Головна передача",r"головн.{0,10}передач|главн.{0,10}передач|диференціал|дифференциал"),
  ("Привід коліс",r"привід кол|привод кол|шрус|піввісь|полуось"),
  ("Карданна передача",r"кардан")),
 (("Передня підвіска",r"передн.{0,20}підвіск|передн.{0,20}подвес"),
  ("Задня підвіска",r"задн.{0,20}підвіск|задн.{0,20}подвес"),
  ("Амортизатори та пружини",r"амортиз|пружин"),
  ("Маточини та підшипники",r"маточин|ступиц|підшипник|подшипник"),
  ("Колеса та шини",r"колес|коліс|шин")),
 (("Кермовий механізм",r"рейк|механізм|механизм"),
  ("Кермові тяги та наконечники",r"тяг|наконеч"),
  ("Підсилювач керма",r"підсилювач|усилител|гур|егур")),
 (("Гальмівні диски та колодки",r"диск|колодк"),
  ("Гальмівні супорти",r"супорт|суппорт"),
  ("Гальмівні магістралі",r"магістрал|магистрал|шланг"),
  ("ABS та електроніка гальм",r"abs|абс")),
 (("Двері та крила",r"двер|крил|крыл"),
  ("Капот і бампери",r"капот|бампер"),
  ("Замки та механізми",r"замок|замк"),
  ("Дзеркала",r"дзеркал|зеркал"),
  ("Скло та ущільнювачі",r"скло|стекл|ущільнювач|уплотн")),
 (("Сидіння",r"сидін|сиден"),
  ("Панель приладів",r"панел|торпед"),
  ("Оздоблення салону",r"оздоблен|отделк|обшив"),
  ("Обладнання салону",r"салон|інтер|интер")),
 (("Стартери та генератори",r"стартер|генератор"),
  ("Проводка та живлення",r"провод|джгут|жгут|акумулятор"),
  ("Блоки керування та датчики",r"блок|датчик|сенсор|ecu|есu"),
  ("Реле та запобіжники",r"реле|запобіжник|предохран")),
 (("Передні фари",r"передн.{0,15}фар|фара"),
  ("Задні ліхтарі",r"задн.{0,15}ліхтар|задн.{0,15}фонар"),
  ("Внутрішнє освітлення",r"внутрішн|салон"),
  ("Очищення та омивання фар",r"очищ.{0,15}фар|очистк.{0,15}фар|омив.{0,15}фар")),
 (("Кондиціонер",r"кондиціон|кондиционер|компресор"),
  ("Опалення",r"опален|отоплен|пічк|печк"),
  ("Вентиляція",r"вентиляц|вентилятор"),
  ("Клімат-контроль",r"клімат|климат")),
 (("Подушки безпеки",r"подушк"),
  ("Ремені безпеки",r"ремен.{0,15}безопас|ремін.{0,15}безпек"),
  ("Датчики та системи безпеки",r"датчик|безпек|безопас")),
 (("Причіпне обладнання",r"причіп|прицеп|фаркоп"),
  ("Комплектувальні та кріплення",r"комплект|кріплен|крепеж"),
  ("Технічне обслуговування",r"обслугов|сервіс|уход|догляд|фільтр|фильтр"),
  ("Додаткове обладнання",r"обладнан|оборудован")),
)
_SUB_PATTERNS=tuple(tuple((label,re.compile(pattern,re.IGNORECASE)) for label,pattern in row) for row in SUBCATEGORIES)
def propose_subcategory(section: str | None, category: str, subcategory: str, part_name: str) -> dict:
    """Conservative subsection suggestion within the section, never a persisted ID."""
    if section not in SECTIONS:
        return {"subcategory":None,"status":"review_required","reason":"unknown_section"}
    index=SECTIONS.index(section)
    for source,value in (("subcategory",subcategory),("part_name",part_name),("category",category)):
        if not value:continue
        if _BROAD.search(value):
            return {"subcategory":None,"status":"review_required","reason":"mixed_systems","evidence":source}
        matches={label for label,pattern in _SUB_PATTERNS[index] if pattern.search(value)}
        if len(matches)==1:
            return {"subcategory":next(iter(matches)),"status":"suggested","reason":"rule_match","evidence":source}
        if len(matches)>1:
            return {"subcategory":None,"status":"review_required","reason":"multiple_subcategories","evidence":source}
    return {"subcategory":None,"status":"review_required","reason":"no_confident_match"}

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
