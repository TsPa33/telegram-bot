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
    price_label: str | None = None,
    photo_id: str = "",
) -> dict:
    service = {
        "category": category,
        "title": title,
        "city": city,
        "address": address,
        "description": description,
        "website": website,
        "photo_id": photo_id,
        "price": price,
    }

    if price_label:
        service["price_label"] = price_label

    return service


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
            "shop_name": "VoltDrive Auto Electric",
            "name": "VoltDrive Auto Electric",
            "phone": "+380675557700",
            "city": "Дніпро",
            "description": "Компʼютерна діагностика, ремонт електропроводки, стартерів, генераторів, АКБ та електронних систем авто.",
            "website": "https://carpot.demo/autoelektryk",
        },
        "config": {
            "theme": {"scheme": "electric_premium_dark"},
            "header": {"title": "VoltDrive Auto Electric", "logo": ""},
            "hero": {
                "title": "Компʼютерна діагностика та автоелектрик",
                "subtitle": "Знаходимо причину несправності, перевіряємо електроніку, АКБ, проводку, стартери та генератори.",
                "banners": [],
            },
            "contacts": {
                "phones": ["+380675557700", "+380505557700"],
                "address": "м. Дніпро, просп. Слобожанський, 52",
                "messengers": {"telegram": "https://t.me/carpot_demo_electric", "whatsapp": "", "viber": ""},
                "socials": {"instagram": "https://instagram.com/carpot.demo.electric", "facebook": ""},
                "map_embed": "",
            },
            "modules": {"services": True, "contacts": True, "map": True, "cars": False, "products": False},
        },
        "services": [
            _service(category="Автоелектрик", title="Компʼютерна діагностика", city="Дніпро", address="просп. Слобожанський, 52", description="OBD/ECU діагностика, зчитування помилок, live data та перевірка електронних систем.", website="https://carpot.demo/autoelektryk", price=700),
            _service(category="Автоелектрик", title="Ремонт електропроводки", city="Дніпро", address="просп. Слобожанський, 52", description="Пошук обривів, коротких замикань, проблем із масою та відновлення джгутів проводки.", website="https://carpot.demo/autoelektryk", price=1200),
            _service(category="Автоелектрик", title="Стартер / генератор", city="Дніпро", address="просп. Слобожанський, 52", description="Діагностика, демонтаж, ремонт або заміна стартера й генератора.", website="https://carpot.demo/autoelektryk", price=1300),
            _service(category="Автоелектрик", title="АКБ та зарядка", city="Дніпро", address="просп. Слобожанський, 52", description="Перевірка акумулятора, генератора, зарядки, витоку струму та проблем із запуском.", website="https://carpot.demo/autoelektryk", price=600),
            _service(category="Автоелектрик", title="Встановлення обладнання", city="Дніпро", address="просп. Слобожанський, 52", description="Камери, парктроніки, сигналізації, мультимедіа, реєстратори та додаткове світло.", website="https://carpot.demo/autoelektryk", price=1500),
            _service(category="Автоелектрик", title="Діагностика CAN / електроніки", city="Дніпро", address="просп. Слобожанський, 52", description="Перевірка CAN-шини, блоків керування, датчиків та складних електронних несправностей.", website="https://carpot.demo/autoelektryk", price=1600),
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
                        "oem": "03L100036R",
                        "badge": "TOP",
                        "stock": "В наявності",
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
                        "oem": "24008636404",
                        "badge": "OEM",
                        "stock": "Перевірено",
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
                        "oem": "4G0941033",
                        "badge": "NEW",
                        "stock": "Готово до відправки",
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
                        "oem": "5211906C90",
                        "badge": "SALE",
                        "stock": "В наявності",
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
                        "oem": "A2127200205",
                        "badge": "OEM",
                        "stock": "Перевірено",
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
                        "oem": "52107915712",
                        "badge": "HOT",
                        "stock": "В наявності",
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
                        "oem": "BV613200AB",
                        "badge": "TOP",
                        "stock": "Готово до відправки",
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
                        "oem": "5Q0413031",
                        "badge": "NEW",
                        "stock": "Перевірено",
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


DEMO_STANDARD_SUBDOMAIN_TYPES = {
    "demo-sto": "sto",
    "demo-tow": "tow",
    "demo-shynomontag": "tire",
}


def _map_embed(address: str) -> str:
    query = address.replace(" ", "+")
    return (
        '<iframe src="https://www.google.com/maps?q='
        f'{query}&output=embed" loading="lazy" '
        'referrerpolicy="no-referrer-when-downgrade"></iframe>'
    )


DEMO_PRESETS["sto"] = {
    "seller": {
        "shop_name": "CarPot AutoService",
        "name": "CarPot AutoService",
        "phone": "+380671112233",
        "city": "Київ",
        "description": "СТО та автосервіс: діагностика, ремонт ходової, заміна мастила, гальмівна система та сезонна підготовка авто.",
        "website": "https://worker-production-e30f.up.railway.app/site/demo-sto",
    },
    "config": {
        "theme": {"scheme": "premium_dark"},
        "header": {"title": "CarPot AutoService", "logo": ""},
        "hero": {
            "enabled": True,
            "eyebrow": "СТО · ДІАГНОСТИКА · РЕМОНТ",
            "title": "СТО та ремонт авто у вашому місті",
            "subtitle": "Діагностика, ремонт ходової, заміна мастила, гальмівна система та підготовка авто до сезону. Залиште заявку — ми звʼяжемося з вами.",
            "banners": [
                "https://images.unsplash.com/photo-1487754180451-c456f719a1fc?auto=format&fit=crop&w=1800&q=80",
            ],
        },
        "contacts": {
            "phones": ["+380671112233"],
            "address": "м. Київ, вул. Автосервісна, 12",
            "hours": "Пн-Сб 09:00–19:00",
            "messengers": {
                "telegram": "https://t.me/CarPotbot",
                "whatsapp": "380671112233",
                "viber": "+380671112233",
            },
            "socials": {"instagram": "", "facebook": ""},
            "map_embed": _map_embed("м. Київ, вул. Автосервісна, 12"),
        },
        "modules": {"services": True, "cars": False, "contacts": True, "map": True, "products": False},
        "footer": {"enabled": True, "text": "CarPot AutoService — якісний автосервіс, прозорі ціни та запис через Telegram."},
    },
    "services": [
        _service(category="СТО", title="Компʼютерна діагностика", city="Київ", address="вул. Автосервісна, 12", description="Зчитування помилок, перевірка електронних систем та зрозумілі рекомендації майстра.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=500),
        _service(category="СТО", title="Заміна мастила та фільтрів", city="Київ", address="вул. Автосервісна, 12", description="Підбір мастила, заміна фільтрів і швидка базова перевірка авто перед виїздом.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=700),
        _service(category="СТО", title="Ремонт ходової", city="Київ", address="вул. Автосервісна, 12", description="Діагностика підвіски, заміна важелів, амортизаторів, тяг, сайлентблоків і втулок.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=900),
        _service(category="СТО", title="Заміна гальмівних колодок", city="Київ", address="вул. Автосервісна, 12", description="Огляд дисків і супортів, заміна колодок та перевірка гальмівної системи.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=800),
        _service(category="СТО", title="Діагностика двигуна", city="Київ", address="вул. Автосервісна, 12", description="Перевірка роботи двигуна, датчиків, витоків і симптомів перед ремонтом.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=600),
        _service(category="СТО", title="Підготовка авто до сезону", city="Київ", address="вул. Автосервісна, 12", description="Комплексна перевірка рідин, АКБ, шин, гальм і підвіски перед зимою або літом.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=1200),
        _service(category="СТО", title="Заміна акумулятора", city="Київ", address="вул. Автосервісна, 12", description="Перевірка зарядки, підбір АКБ, встановлення та контроль запуску авто.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=400),
        _service(category="СТО", title="Консультація майстра", city="Київ", address="вул. Автосервісна, 12", description="Швидко підкажемо, з чого почати ремонт, та зорієнтуємо по термінах і бюджету.", website="https://worker-production-e30f.up.railway.app/site/demo-sto", price=0, price_label="безкоштовно"),
    ],
}

DEMO_PRESETS["tow"] = {
    "seller": {
        "shop_name": "CarPot Tow Service",
        "name": "CarPot Tow Service",
        "phone": "+380672223344",
        "city": "Львів",
        "description": "Евакуатор 24/7, допомога після ДТП, запуск акумулятора та транспортування авто по місту й області.",
        "website": "https://worker-production-e30f.up.railway.app/site/demo-tow",
    },
    "config": {
        "theme": {"scheme": "premium_dark"},
        "header": {"title": "CarPot Tow Service", "logo": ""},
        "hero": {
            "enabled": True,
            "eyebrow": "ЕВАКУАТОР · 24/7 · ДОПОМОГА В ДОРОЗІ",
            "title": "Евакуатор 24/7 та допомога в дорозі",
            "subtitle": "Швидка подача евакуатора, перевезення авто, допомога після ДТП, запуск акумулятора та транспортування по місту й області.",
            "banners": [
                "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1800&q=80",
            ],
        },
        "contacts": {
            "phones": ["+380672223344"],
            "address": "м. Львів, вул. Дорожня, 8",
            "hours": "Цілодобово",
            "messengers": {
                "telegram": "https://t.me/CarPotbot",
                "whatsapp": "380672223344",
                "viber": "+380672223344",
            },
            "socials": {"instagram": "", "facebook": ""},
            "map_embed": _map_embed("м. Львів, вул. Дорожня, 8"),
        },
        "modules": {"services": True, "cars": False, "contacts": True, "map": True, "products": False},
        "footer": {"enabled": True, "text": "CarPot Tow Service — евакуатор 24/7, місто та область, заявки з сайту і Telegram."},
    },
    "services": [
        _service(category="Евакуатор", title="Евакуація легкового авто", city="Львів", address="вул. Дорожня, 8", description="Подача платформи для легкового авто з безпечним завантаженням і фіксацією.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=1200),
        _service(category="Евакуатор", title="Евакуатор після ДТП", city="Львів", address="вул. Дорожня, 8", description="Акуратне завантаження пошкодженого авто та доставка на СТО, стоянку або за адресою.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=1500),
        _service(category="Евакуатор", title="Перевезення авто по місту", city="Львів", address="вул. Дорожня, 8", description="Перевеземо авто між районами міста, до сервісу, дилера або місця зберігання.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=1000),
        _service(category="Евакуатор", title="Перевезення авто між містами", city="Львів", address="вул. Дорожня, 8", description="Міжміська доставка авто з попереднім розрахунком маршруту та вартості.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=25, price_label="від 25 грн/км"),
        _service(category="Евакуатор", title="Допомога при розрядженому АКБ", city="Львів", address="вул. Дорожня, 8", description="Приїдемо, допоможемо запустити авто та підкажемо, чи потрібна заміна акумулятора.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=500),
        _service(category="Евакуатор", title="Доставка авто на СТО", city="Львів", address="вул. Дорожня, 8", description="Доставимо несправне авто на сервіс і передамо майстру без зайвої логістики для власника.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=900),
        _service(category="Евакуатор", title="Евакуація мотоцикла", city="Львів", address="вул. Дорожня, 8", description="Перевезення мотоциклів і скутерів із додатковою фіксацією на платформі.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=900),
        _service(category="Евакуатор", title="Терміновий виїзд", city="Львів", address="вул. Дорожня, 8", description="Пріоритетна подача екіпажу, коли авто потрібно забрати максимально швидко.", website="https://worker-production-e30f.up.railway.app/site/demo-tow", price=0, price_label="за домовленістю"),
    ],
}

DEMO_PRESETS["tire"] = {
    "seller": {
        "shop_name": "CarPot Tyre Service",
        "name": "CarPot Tyre Service",
        "phone": "+380673334455",
        "city": "Тернопіль",
        "description": "Шиномонтаж, балансування, ремонт проколів, зберігання коліс та сезонний запис через Telegram.",
        "website": "https://worker-production-e30f.up.railway.app/site/demo-shynomontag",
    },
    "config": {
        "theme": {"scheme": "light_blue"},
        "header": {"title": "CarPot Tyre Service", "logo": ""},
        "hero": {
            "enabled": True,
            "eyebrow": "ШИНОМОНТАЖ · БАЛАНСУВАННЯ · СЕЗОН",
            "title": "Шиномонтаж та сезонна заміна шин",
            "subtitle": "Заміна шин, балансування, ремонт проколів, зберігання коліс та підготовка авто до сезону. Запис через Telegram або заявку на сайті.",
            "banners": [
                "https://images.unsplash.com/photo-1580273916550-e323be2ae537?auto=format&fit=crop&w=1800&q=80",
            ],
        },
        "contacts": {
            "phones": ["+380673334455"],
            "address": "м. Тернопіль, вул. Шинна, 5",
            "hours": "Пн-Нд 08:00–20:00",
            "messengers": {
                "telegram": "https://t.me/CarPotbot",
                "whatsapp": "380673334455",
                "viber": "+380673334455",
            },
            "socials": {"instagram": "", "facebook": ""},
            "map_embed": _map_embed("м. Тернопіль, вул. Шинна, 5"),
        },
        "modules": {"services": True, "cars": False, "contacts": True, "map": True, "products": False},
        "footer": {"enabled": True, "text": "CarPot Tyre Service — шиномонтаж, балансування, сезонне зберігання та запис без черги."},
    },
    "services": [
        _service(category="Шиномонтаж", title="Заміна шин R13–R15", city="Тернопіль", address="вул. Шинна, 5", description="Швидка сезонна заміна шин для компактних авто з перевіркою стану коліс.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=600),
        _service(category="Шиномонтаж", title="Заміна шин R16–R18", city="Тернопіль", address="вул. Шинна, 5", description="Монтаж і демонтаж шин для легкових авто та кросоверів із дбайливим ставленням до дисків.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=800),
        _service(category="Шиномонтаж", title="Балансування коліс", city="Тернопіль", address="вул. Шинна, 5", description="Точне балансування кожного колеса для комфортної їзди без вібрацій на швидкості.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=150, price_label="від 150 грн/колесо"),
        _service(category="Шиномонтаж", title="Ремонт проколу", city="Тернопіль", address="вул. Шинна, 5", description="Професійний ремонт проколів, герметизація борту та контроль тиску після роботи.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=250),
        _service(category="Шиномонтаж", title="Підкачка шин", city="Тернопіль", address="вул. Шинна, 5", description="Перевірка й корекція тиску відповідно до рекомендацій для вашого авто.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=50),
        _service(category="Шиномонтаж", title="Зберігання шин", city="Тернопіль", address="вул. Шинна, 5", description="Сезонне зберігання комплекту шин або коліс у сухому приміщенні з маркуванням.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=1200, price_label="від 1200 грн/сезон"),
        _service(category="Шиномонтаж", title="Перевірка тиску", city="Тернопіль", address="вул. Шинна, 5", description="Безкоштовно перевіримо тиск і підкажемо, коли краще планувати сезонну заміну.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=0, price_label="безкоштовно"),
        _service(category="Шиномонтаж", title="Сезонний запис", city="Тернопіль", address="вул. Шинна, 5", description="Попереднє бронювання зручного часу, щоб пройти сезон без черг і очікування.", website="https://worker-production-e30f.up.railway.app/site/demo-shynomontag", price=0, price_label="за попереднім бронюванням"),
    ],
}


_DEMO_STANDARD_MODULES = {
    "pricing": True,
    "gallery": True,
    "works": True,
    "cta": True,
    "reviews": True,
}

_DEMO_STANDARD_CONTENT = {
    "sto": {
        "pricing": {
            "title": "Наші ціни",
            "subtitle": "Популярні роботи для швидкого старту. Точну суму підтвердимо після діагностики.",
            "items": [
                {"title": "Компʼютерна діагностика", "prefix": "від", "price": "500 грн", "description": "OBD-сканування, перевірка помилок і рекомендації майстра."},
                {"title": "Заміна мастила", "prefix": "від", "price": "700 грн", "description": "Підбір мастила, фільтрів і базовий огляд авто."},
                {"title": "Ремонт ходової", "prefix": "від", "price": "900 грн", "description": "Діагностика підвіски та заміна зношених елементів."},
                {"title": "Гальмівна система", "prefix": "від", "price": "800 грн", "description": "Колодки, диски, супорти та контроль безпеки."},
                {"title": "Підготовка до сезону", "prefix": "від", "price": "1200 грн", "description": "Комплексна перевірка перед зимою або літнім сезоном."},
                {"title": "Консультація майстра", "price": "безкоштовно", "description": "Підкажемо оптимальний план ремонту та бюджет."},
            ],
        },
        "gallery": {
            "title": "Галерея сервісу",
            "subtitle": "Робочі зони, обладнання та процес обслуговування авто.",
            "images": [
                {"url": "https://images.unsplash.com/photo-1487754180451-c456f719a1fc?auto=format&fit=crop&w=900&q=80", "alt": "СТО бокс"},
                {"url": "https://images.unsplash.com/photo-1606577924006-27d39b132ae2?auto=format&fit=crop&w=900&q=80", "alt": "Ремонт авто"},
                {"url": "https://images.unsplash.com/photo-1625047509168-a7026f36de04?auto=format&fit=crop&w=900&q=80", "alt": "Майстерня"},
                {"url": "https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?auto=format&fit=crop&w=900&q=80", "alt": "Обслуговування"},
            ],
        },
        "works": {
            "title": "Наші роботи",
            "subtitle": "Типові задачі, які формують довіру до сервісу ще до першого дзвінка.",
            "items": [
                {"title": "Ремонт ходової BMW", "badge": "Підвіска", "description": "Провели діагностику, замінили важелі та стабілізували керованість авто.", "image": "https://images.unsplash.com/photo-1606577924006-27d39b132ae2?auto=format&fit=crop&w=900&q=80", "before": "стук і люфт", "after": "тиха робота підвіски"},
                {"title": "ТО перед поїздкою", "badge": "Сервіс", "description": "Замінили мастило, фільтри, перевірили гальма, АКБ та рідини перед маршрутом.", "image": "https://images.unsplash.com/photo-1625047509168-a7026f36de04?auto=format&fit=crop&w=900&q=80"},
                {"title": "Діагностика Check Engine", "badge": "Діагностика", "description": "Знайшли причину помилки, узгодили ремонт і віддали авто з прозорим звітом.", "image": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=900&q=80"},
            ],
        },
        "cta": {"title": "Потрібна консультація майстра?", "text": "Опишіть симптоми — ми підкажемо, чи потрібна діагностика, які терміни та орієнтовний бюджет.", "telegram_text": "Telegram", "phone_text": "Подзвонити", "lead_text": "Залишити заявку"},
        "reviews": {"title": "Відгуки клієнтів", "subtitle": "Клієнти цінують швидкий запис, зрозумілі ціни та фото-звіт після робіт.", "items": [{"name": "Олександр", "text": "Швидко знайшли причину стуку, погодили кошторис і зробили в той самий день.", "stars": 5}, {"name": "Марина", "text": "Записалась через сайт, майстер пояснив усе простими словами. Дуже зручно.", "stars": 5}, {"name": "Ігор", "text": "Після ТО авто готове до дороги, отримав рекомендації на майбутнє.", "stars": 5}]},
    },
    "tow": {
        "pricing": {"title": "Тарифи евакуатора", "subtitle": "Базові тарифи для міста й області. Міжміські маршрути рахуємо індивідуально.", "items": [{"title": "Евакуація легкового авто", "prefix": "від", "price": "1200 грн", "description": "Подача платформи та безпечне завантаження."}, {"title": "Евакуатор після ДТП", "prefix": "від", "price": "1500 грн", "description": "Акуратне транспортування пошкодженого авто."}, {"title": "Перевезення по місту", "prefix": "від", "price": "1000 грн", "description": "Доставка до СТО, стоянки або за адресою."}, {"title": "Міжміська доставка", "prefix": "від", "price": "25 грн/км", "description": "Попередній розрахунок маршруту та часу."}, {"title": "Запуск АКБ", "prefix": "від", "price": "500 грн", "description": "Допомога при розрядженому акумуляторі."}, {"title": "Терміновий виїзд", "price": "за домовленістю", "description": "Пріоритетна подача екіпажу."}]},
        "gallery": {"title": "Галерея виїздів", "subtitle": "Евакуатор у роботі: місто, траса, доставка на СТО.", "images": [{"url": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=900&q=80", "alt": "Авто на дорозі"}, {"url": "https://images.unsplash.com/photo-1542362567-b07e54358753?auto=format&fit=crop&w=900&q=80", "alt": "Автомобіль"}, {"url": "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?auto=format&fit=crop&w=900&q=80", "alt": "Дорога"}, {"url": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=900&q=80", "alt": "Транспортування"}]},
        "works": {"title": "Наші роботи", "subtitle": "Сценарії, де швидкість і акуратність критично важливі.", "items": [{"title": "Евакуація після ДТП", "badge": "Терміново", "description": "Забрали пошкоджене авто з дороги та доставили на СТО без додаткових ризиків.", "image": "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=900&q=80"}, {"title": "Доставка авто на сервіс", "badge": "Місто", "description": "Перевезли несправний автомобіль до майстра та передали ключі відповідальному співробітнику.", "image": "https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?auto=format&fit=crop&w=900&q=80"}, {"title": "Міжміський маршрут", "badge": "Область", "description": "Погодили маршрут, час подачі та доставили авто власнику в інше місто.", "image": "https://images.unsplash.com/photo-1449965408869-eaa3f722e40d?auto=format&fit=crop&w=900&q=80"}]},
        "cta": {"title": "Потрібен евакуатор зараз?", "text": "Надішліть геолокацію у Telegram або залиште номер — диспетчер швидко уточнить адресу й подачу.", "telegram_text": "Telegram", "phone_text": "Подзвонити", "lead_text": "Залишити заявку"},
        "reviews": {"title": "Відгуки водіїв", "subtitle": "Клієнти звертаються, коли важлива швидка подача та зрозумілий тариф.", "items": [{"name": "Андрій", "text": "Приїхали швидко після ДТП, акуратно завантажили авто і довезли до сервісу.", "stars": 5}, {"name": "Наталія", "text": "Диспетчер одразу назвав ціну й час подачі. Без сюрпризів.", "stars": 5}, {"name": "Віталій", "text": "Виручили вночі з розрядженим акумулятором. Рекомендую.", "stars": 5}]},
    },
    "tire": {
        "pricing": {"title": "Ціни на шиномонтаж", "subtitle": "Популярні послуги для сезонної заміни, балансування та догляду за колесами.", "items": [{"title": "Заміна шин R13–R15", "prefix": "від", "price": "600 грн", "description": "Комплексна заміна для компактних авто."}, {"title": "Заміна шин R16–R18", "prefix": "від", "price": "800 грн", "description": "Монтаж для легкових авто та кросоверів."}, {"title": "Балансування коліс", "prefix": "від", "price": "150 грн/колесо", "description": "Точне балансування без вібрацій."}, {"title": "Ремонт проколу", "prefix": "від", "price": "250 грн", "description": "Герметизація та контроль тиску."}, {"title": "Зберігання шин", "prefix": "від", "price": "1200 грн/сезон", "description": "Сухе зберігання з маркуванням комплектів."}, {"title": "Перевірка тиску", "price": "безкоштовно", "description": "Швидка перевірка перед дорогою."}]},
        "gallery": {"title": "Галерея шиномонтажу", "subtitle": "Зона монтажу, балансування та сезонного обслуговування.", "images": [{"url": "https://images.unsplash.com/photo-1580273916550-e323be2ae537?auto=format&fit=crop&w=900&q=80", "alt": "Авто"}, {"url": "https://images.unsplash.com/photo-1600706432502-77a0e2e327a9?auto=format&fit=crop&w=900&q=80", "alt": "Колесо"}, {"url": "https://images.unsplash.com/photo-1609521263047-f8f205293f24?auto=format&fit=crop&w=900&q=80", "alt": "Шини"}, {"url": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=900&q=80", "alt": "Авто після сервісу"}]},
        "works": {"title": "Наші роботи", "subtitle": "Приклади сезонних задач, які клієнти часто замовляють онлайн.", "items": [{"title": "Сезонний шиномонтаж", "badge": "Сезон", "description": "Замінили комплект шин, перевірили тиск і стан протектора перед сезоном.", "image": "https://images.unsplash.com/photo-1600706432502-77a0e2e327a9?auto=format&fit=crop&w=900&q=80"}, {"title": "Балансування коліс", "badge": "Комфорт", "description": "Прибрали вібрацію на швидкості після точного балансування комплекту.", "image": "https://images.unsplash.com/photo-1503736334956-4c8f8e92946d?auto=format&fit=crop&w=900&q=80"}, {"title": "Ремонт проколу", "badge": "Швидко", "description": "Відремонтували прокол, перевірили герметичність і повернули авто в дорогу.", "image": "https://images.unsplash.com/photo-1502877338535-766e1452684a?auto=format&fit=crop&w=900&q=80"}]},
        "cta": {"title": "Записатися на шиномонтаж?", "text": "Оберіть зручний час через Telegram або залиште заявку — менеджер підтвердить слот без черги.", "telegram_text": "Telegram", "phone_text": "Подзвонити", "lead_text": "Залишити заявку"},
        "reviews": {"title": "Відгуки клієнтів", "subtitle": "Водії відзначають швидкий запис, чисту роботу та точне балансування.", "items": [{"name": "Сергій", "text": "Перевзули авто без черги, балансування ідеальне — вібрації зникли.", "stars": 5}, {"name": "Олена", "text": "Зручно записалась через Telegram, приїхала на свій час і швидко поїхала.", "stars": 5}, {"name": "Роман", "text": "Прокол зробили за 20 хвилин і перевірили всі колеса.", "stars": 5}]},
    },
}

for _demo_key, _demo_content in _DEMO_STANDARD_CONTENT.items():
    _config = DEMO_PRESETS[_demo_key].setdefault("config", {})
    _config.setdefault("modules", {}).update(_DEMO_STANDARD_MODULES)
    _config.update(_demo_content)


def get_demo_render_preset(subdomain: str) -> dict | None:
    demo_type = DEMO_STANDARD_SUBDOMAIN_TYPES.get(str(subdomain or "").strip().lower())
    if not demo_type:
        return None

    preset = DEMO_PRESETS.get(demo_type)
    if not preset:
        return None

    return {**copy.deepcopy(preset), "demo_type": demo_type}


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

    if isinstance(current_banners, list) and current_banners:
        config.setdefault("hero", {})["banners"] = current_banners

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
