import copy
import json

from bot.database.repositories.seller_repo import update_seller_demo_profile
from bot.database.repositories.service_repo import (
    bulk_create_services,
    delete_services_by_seller,
)
from bot.database.repositories.site_repo import get_site_by_id, update_demo_site_config
from bot.services.site_config import merge_with_default

SITE_BASE_URL = "https://worker-production-e30f.up.railway.app/site"

DEMO_SEED_TYPES = {
    "tire": "🛞 Шиномонтаж",
    "sto": "🛠 СТО",
    "tow": "🚛 Евакуатор",
    "electric": "⚡ Автоелектрик",
    "parts": "🚗 Автозапчастини / Розборка",
}


def _service(
    *,
    category: str,
    title: str,
    city: str,
    address: str,
    description: str,
    website: str,
    price: int,
) -> dict:
    return {
        "category": category,
        "title": title,
        "city": city,
        "address": address,
        "description": description,
        "website": website,
        "photo_id": "",
        "price": price,
    }


DEMO_PRESETS = {
    "tire": {
        "seller": {
            "shop_name": "CARPOT Demo Шиномонтаж",
            "name": "Demo Шиномонтаж CARPOT",
            "phone": "+380671112233",
            "city": "Київ",
            "description": "Демо майстерня шиномонтажу: сезонна заміна шин, балансування, ремонт проколів та зберігання комплектів.",
            "website": "https://carpot.demo/shynomontag",
        },
        "config": {
            "theme": {"scheme": "light_blue"},
            "header": {"title": "CARPOT Demo Шиномонтаж", "logo": ""},
            "hero": {
                "title": "Шиномонтаж без черг у Києві",
                "subtitle": "Швидко перевзуємо авто, відбалансуємо колеса та підготуємо шини до сезону.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380671112233", "+380501112233"],
                "address": "м. Київ, вул. Автомобільна, 12",
                "messengers": {
                    "telegram": "https://t.me/carpot_demo_tire",
                    "whatsapp": "",
                    "viber": "",
                },
                "socials": {
                    "instagram": "https://instagram.com/carpot.demo.tire",
                    "facebook": "",
                },
                "map_embed": "",
            },
            "modules": {"services": True, "cars": False, "contacts": True, "map": True},
        },
        "services": [
            _service(category="Шиномонтаж", title="Шиномонтаж легкових авто", city="Київ", address="вул. Автомобільна, 12", description="Зняття, монтаж і перевірка коліс для легкових авто та кросоверів.", website="https://carpot.demo/shynomontag", price=450),
            _service(category="Шиномонтаж", title="Балансування коліс", city="Київ", address="вул. Автомобільна, 12", description="Точне балансування на сучасному стенді для комфортної їзди без вібрацій.", website="https://carpot.demo/shynomontag", price=300),
            _service(category="Шиномонтаж", title="Ремонт проколів", city="Київ", address="вул. Автомобільна, 12", description="Швидкий ремонт проколів, герметизація борту та перевірка тиску.", website="https://carpot.demo/shynomontag", price=250),
            _service(category="Шиномонтаж", title="Сезонна заміна шин", city="Київ", address="вул. Автомобільна, 12", description="Комплексна сезонна заміна шин із оглядом стану протектора.", website="https://carpot.demo/shynomontag", price=900),
            _service(category="Шиномонтаж", title="Зберігання шин", city="Київ", address="вул. Автомобільна, 12", description="Сезонне зберігання комплектів шин у сухому складському приміщенні.", website="https://carpot.demo/shynomontag", price=1200),
        ],
    },
    "sto": {
        "seller": {
            "shop_name": "CARPOT Demo СТО",
            "name": "Demo СТО CARPOT",
            "phone": "+380672224455",
            "city": "Львів",
            "description": "Демо СТО для планового обслуговування, діагностики, ремонту ходової та гальмівної системи.",
            "website": "https://carpot.demo/sto",
        },
        "config": {
            "theme": {"scheme": "default"},
            "header": {"title": "CARPOT Demo СТО", "logo": ""},
            "hero": {
                "title": "СТО повного циклу у Львові",
                "subtitle": "Діагностика, ТО та ремонт авто з прозорими цінами й записом онлайн.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380672224455", "+380932224455"],
                "address": "м. Львів, вул. Городоцька, 214",
                "messengers": {"telegram": "https://t.me/carpot_demo_sto", "whatsapp": "", "viber": ""},
                "socials": {"instagram": "https://instagram.com/carpot.demo.sto", "facebook": ""},
                "map_embed": "",
            },
            "modules": {"services": True, "cars": False, "contacts": True, "map": True},
        },
        "services": [
            _service(category="СТО", title="Діагностика авто", city="Львів", address="вул. Городоцька, 214", description="Огляд основних вузлів авто перед ремонтом або купівлею.", website="https://carpot.demo/sto", price=700),
            _service(category="СТО", title="Заміна мастила", city="Львів", address="вул. Городоцька, 214", description="Заміна моторного мастила, фільтрів та базова перевірка авто.", website="https://carpot.demo/sto", price=600),
            _service(category="СТО", title="Ремонт ходової", city="Львів", address="вул. Городоцька, 214", description="Діагностика та заміна амортизаторів, важелів, сайлентблоків і тяг.", website="https://carpot.demo/sto", price=1200),
            _service(category="СТО", title="Гальмівна система", city="Львів", address="вул. Городоцька, 214", description="Заміна колодок, дисків, рідини та профілактика супортів.", website="https://carpot.demo/sto", price=900),
            _service(category="СТО", title="Компʼютерна діагностика", city="Львів", address="вул. Городоцька, 214", description="Зчитування помилок, перевірка датчиків і рекомендації щодо ремонту.", website="https://carpot.demo/sto", price=500),
        ],
    },
    "tow": {
        "seller": {
            "shop_name": "CARPOT Demo Евакуатор",
            "name": "Demo Евакуатор CARPOT",
            "phone": "+380673336677",
            "city": "Одеса",
            "description": "Демо служба евакуації авто 24/7: місто, міжміські перевезення та допомога на дорозі.",
            "website": "https://carpot.demo/evakuator",
        },
        "config": {
            "theme": {"scheme": "premium_dark"},
            "header": {"title": "CARPOT Demo Евакуатор", "logo": ""},
            "hero": {
                "title": "Евакуатор 24/7 в Одесі",
                "subtitle": "Швидко приїдемо, безпечно завантажимо та доставимо авто за адресою.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380673336677", "+380503336677"],
                "address": "м. Одеса, вул. Балківська, 88",
                "messengers": {"telegram": "https://t.me/carpot_demo_tow", "whatsapp": "", "viber": ""},
                "socials": {"instagram": "https://instagram.com/carpot.demo.tow", "facebook": ""},
                "map_embed": "",
            },
            "modules": {"services": True, "cars": False, "contacts": True, "map": True},
        },
        "services": [
            _service(category="Евакуатор", title="Евакуатор 24/7", city="Одеса", address="вул. Балківська, 88", description="Цілодобова евакуація легкових авто та кросоверів по Одесі.", website="https://carpot.demo/evakuator", price=1200),
            _service(category="Евакуатор", title="Перевезення авто по місту", city="Одеса", address="вул. Балківська, 88", description="Акуратне транспортування авто між районами міста.", website="https://carpot.demo/evakuator", price=1000),
            _service(category="Евакуатор", title="Доставка авто між містами", city="Одеса", address="вул. Балківська, 88", description="Міжміські перевезення авто з фіксацією та контролем маршруту.", website="https://carpot.demo/evakuator", price=3500),
            _service(category="Евакуатор", title="Допомога при ДТП", city="Одеса", address="вул. Балківська, 88", description="Оперативний виїзд після ДТП та доставка авто на СТО або стоянку.", website="https://carpot.demo/evakuator", price=1500),
            _service(category="Евакуатор", title="Підвезення пального / запуск авто", city="Одеса", address="вул. Балківська, 88", description="Доставимо пальне, допоможемо із запуском акумулятора або буксируванням.", website="https://carpot.demo/evakuator", price=700),
        ],
    },
    "electric": {
        "seller": {
            "shop_name": "CARPOT Demo Автоелектрик",
            "name": "Demo Автоелектрик CARPOT",
            "phone": "+380674448899",
            "city": "Дніпро",
            "description": "Демо автоелектрик: діагностика електроніки, ремонт проводки, стартерів, генераторів та додаткове обладнання.",
            "website": "https://carpot.demo/autoelektryk",
        },
        "config": {
            "theme": {"scheme": "neon_dark"},
            "header": {"title": "CARPOT Demo Автоелектрик", "logo": ""},
            "hero": {
                "title": "Автоелектрик із компʼютерною діагностикою",
                "subtitle": "Знаходимо електричні несправності та повертаємо авто до роботи.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380674448899", "+380934448899"],
                "address": "м. Дніпро, просп. Слобожанський, 52",
                "messengers": {"telegram": "https://t.me/carpot_demo_electric", "whatsapp": "", "viber": ""},
                "socials": {"instagram": "https://instagram.com/carpot.demo.electric", "facebook": ""},
                "map_embed": "",
            },
            "modules": {"services": True, "cars": False, "contacts": True, "map": True},
        },
        "services": [
            _service(category="Автоелектрик", title="Компʼютерна діагностика", city="Дніпро", address="просп. Слобожанський, 52", description="Зчитування помилок, live data та перевірка електронних систем авто.", website="https://carpot.demo/autoelektryk", price=600),
            _service(category="Автоелектрик", title="Ремонт електропроводки", city="Дніпро", address="просп. Слобожанський, 52", description="Пошук обривів, коротких замикань та відновлення джгутів проводки.", website="https://carpot.demo/autoelektryk", price=900),
            _service(category="Автоелектрик", title="Генератор / стартер", city="Дніпро", address="просп. Слобожанський, 52", description="Діагностика, демонтаж, ремонт або заміна стартера й генератора.", website="https://carpot.demo/autoelektryk", price=1100),
            _service(category="Автоелектрик", title="Акумуляторна система", city="Дніпро", address="просп. Слобожанський, 52", description="Перевірка АКБ, зарядки, маси та споживання струму в спокої.", website="https://carpot.demo/autoelektryk", price=500),
            _service(category="Автоелектрик", title="Встановлення додаткового обладнання", city="Дніпро", address="просп. Слобожанський, 52", description="Монтаж камер, парктроніків, реєстраторів, сигналізацій та мультимедіа.", website="https://carpot.demo/autoelektryk", price=1300),
        ],
    },
    "parts": {
        "seller": {
            "shop_name": "CARPOT Demo Розборка",
            "name": "Demo Автозапчастини CARPOT",
            "phone": "+380675559900",
            "city": "Харків",
            "description": "Демо магазин автозапчастин із розборки: кузовні деталі, двигуни, КПП, оптика та підбір по VIN.",
            "website": "https://carpot.demo/rozborka",
        },
        "config": {
            "theme": {"scheme": "parts_dark_red"},
            "header": {"title": "CARPOT Demo Розборка", "logo": ""},
            "hero": {
                "title": "Автозапчастини з розборки з підбором по VIN",
                "subtitle": "Допоможемо знайти сумісну деталь, перевіримо стан та організуємо доставку.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380675559900", "+380505559900"],
                "address": "м. Харків, вул. Клочківська, 370",
                "messengers": {"telegram": "https://t.me/carpot_demo_parts", "whatsapp": "", "viber": ""},
                "socials": {"instagram": "https://instagram.com/carpot.demo.parts", "facebook": ""},
                "map_embed": "",
            },
            "modules": {"services": True, "cars": False, "contacts": True, "map": True, "products": True},
            "products": {
                "title": "Каталог автозапчастин",
                "subtitle": "Перевірені запчастини з розборки з підбором по VIN",
                "categories": [
                    "Двигуни",
                    "КПП",
                    "Оптика",
                    "Кузов",
                    "Салон",
                    "Ходова",
                ],
                "items": [
                    {
                        "id": "engine-vw-16-tdi",
                        "category": "Двигуни",
                        "title": "Двигун Volkswagen 1.6 TDI",
                        "brand": "Volkswagen",
                        "condition": "Вживаний, перевірений",
                        "price": "42 000 грн",
                        "image": "",
                        "description": "Двигун у робочому стані, перевірений перед демонтажем.",
                        "sku": "CP-ENG-001",
                    },
                    {
                        "id": "transmission-bmw-8hp",
                        "category": "КПП",
                        "title": "АКПП BMW 8HP",
                        "brand": "BMW",
                        "condition": "Контрактна, перевірена",
                        "price": "58 000 грн",
                        "image": "",
                        "description": "Автоматична коробка передач із перевіркою роботи перед відправкою.",
                        "sku": "CP-TRN-002",
                    },
                    {
                        "id": "headlight-led-audi-a6",
                        "category": "Оптика",
                        "title": "Фара LED Audi A6",
                        "brand": "Audi",
                        "condition": "Оригінал, без тріщин",
                        "price": "12 500 грн",
                        "image": "",
                        "description": "Оригінальна LED фара без пошкоджень корпусу та скла.",
                        "sku": "CP-LGT-003",
                    },
                    {
                        "id": "front-bumper-toyota-camry",
                        "category": "Кузов",
                        "title": "Бампер передній Toyota Camry",
                        "brand": "Toyota",
                        "condition": "Потребує фарбування",
                        "price": "8 900 грн",
                        "image": "",
                        "description": "Передній бампер із цілими кріпленнями, підготовка до фарбування.",
                        "sku": "CP-BDY-004",
                    },
                    {
                        "id": "front-door-mercedes-w212",
                        "category": "Кузов",
                        "title": "Двері передні Mercedes W212",
                        "brand": "Mercedes-Benz",
                        "condition": "Оригінал, рівні",
                        "price": "11 000 грн",
                        "image": "",
                        "description": "Оригінальні передні двері без геометричних пошкоджень.",
                        "sku": "CP-BDY-005",
                    },
                    {
                        "id": "leather-interior-bmw-f10",
                        "category": "Салон",
                        "title": "Салон шкіряний BMW F10",
                        "brand": "BMW",
                        "condition": "Комплект, добрий стан",
                        "price": "26 000 грн",
                        "image": "",
                        "description": "Комплект шкіряного салону в доброму стані для BMW F10.",
                        "sku": "CP-INT-006",
                    },
                    {
                        "id": "steering-rack-ford-focus",
                        "category": "Ходова",
                        "title": "Рульова рейка Ford Focus",
                        "brand": "Ford",
                        "condition": "Перевірена",
                        "price": "7 500 грн",
                        "image": "",
                        "description": "Рульова рейка після перевірки, готова до встановлення.",
                        "sku": "CP-SUS-007",
                    },
                    {
                        "id": "suspension-kit-skoda-octavia",
                        "category": "Ходова",
                        "title": "Комплект ходової Skoda Octavia",
                        "brand": "Skoda",
                        "condition": "Після діагностики",
                        "price": "9 800 грн",
                        "image": "",
                        "description": "Підібраний комплект деталей ходової після діагностики стану.",
                        "sku": "CP-SUS-008",
                    },
                ],
            },
        },
        "services": [
            _service(category="Автозапчастини", title="Запчастини з розборки", city="Харків", address="вул. Клочківська, 370", description="Перевірені вживані запчастини для популярних марок авто в наявності та під замовлення.", website="https://carpot.demo/rozborka", price=500),
            _service(category="Автозапчастини", title="Двигуни та КПП", city="Харків", address="вул. Клочківська, 370", description="Контрактні двигуни, механічні та автоматичні коробки передач із перевіркою стану.", website="https://carpot.demo/rozborka", price=15000),
            _service(category="Автозапчастини", title="Кузовні деталі", city="Харків", address="вул. Клочківська, 370", description="Двері, крила, капоти, бампери та інші кузовні елементи для ремонту авто.", website="https://carpot.demo/rozborka", price=1800),
            _service(category="Автозапчастини", title="Оптика", city="Харків", address="вул. Клочківська, 370", description="Фари, ліхтарі, протитуманки та блоки керування світлом із перевіркою перед відправкою.", website="https://carpot.demo/rozborka", price=1200),
            _service(category="Автозапчастини", title="Підбір запчастин по VIN", city="Харків", address="вул. Клочківська, 370", description="Підберемо сумісні запчастини за VIN-кодом і підкажемо доступні аналоги.", website="https://carpot.demo/rozborka", price=300),
        ],
    },
}


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return copy.deepcopy(value)

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return {}


def _config_with_preserved_banners(site, preset_config: dict) -> dict:
    current_config = _as_dict(site.get("config_draft") or site.get("config_live") or {})
    current_banners = (
        current_config.get("hero", {}).get("banners")
        if isinstance(current_config.get("hero"), dict)
        else None
    )

    config = copy.deepcopy(preset_config)
    config.setdefault("header", {})["logo"] = ""
    config.setdefault("hero", {})["banners"] = current_banners if isinstance(current_banners, list) else []

    return merge_with_default(config)


async def seed_demo_site(site_id: int, demo_type: str) -> dict:
    if demo_type not in DEMO_PRESETS:
        raise ValueError("Невідомий тип demo контенту")

    site = await get_site_by_id(site_id)
    if not site:
        raise ValueError("Демо сайт не знайдено")

    subdomain = str(site.get("subdomain") or "")
    if not subdomain.startswith("demo-"):
        raise PermissionError("Seed доступний тільки для demo сайтів")

    seller_id = site.get("seller_id")
    if not seller_id:
        raise ValueError("У demo сайту не вказаний seller_id")

    preset = DEMO_PRESETS[demo_type]
    config = _config_with_preserved_banners(site, preset["config"])

    await update_seller_demo_profile(seller_id, preset["seller"])
    await delete_services_by_seller(seller_id)
    service_ids = await bulk_create_services(seller_id, preset["services"])
    config_saved = await update_demo_site_config(site_id, config)

    if not config_saved:
        raise RuntimeError("Не вдалося оновити config demo сайту")

    return {
        "subdomain": subdomain,
        "seller_id": seller_id,
        "services_count": len(service_ids),
        "site_url": f"{SITE_BASE_URL}/{subdomain}",
        "demo_type": demo_type,
        "demo_type_label": DEMO_SEED_TYPES[demo_type],
    }
