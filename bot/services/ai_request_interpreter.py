"""Reusable AI-assisted automotive request interpreter.

The interpreter is intentionally narrow: it converts buyer natural language into a
safe structured object. It does not search the database, route sellers, or create
marketplace requests. Those decisions remain in CarPot services/routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any


logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {"parts_search", "service_search", "car_search", "seller_search", "unknown"}
ALLOWED_CATEGORIES = {"parts", "services", "cars", "sellers", "unknown"}
ALLOWED_URGENCY = {"low", "normal", "urgent"}

DEFAULT_AI_REQUEST_MODEL = "gpt-4o-mini"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
MAX_QUERY_LENGTH = 700
MIN_AI_QUERY_LENGTH = 6
AI_TIMEOUT_SECONDS = 6.0

BRAND_ALIASES = {
    "bmw": "BMW",
    "бмв": "BMW",
    "ауді": "Audi",
    "ауди": "Audi",
    "audi": "Audi",
    "vw": "Volkswagen",
    "volkswagen": "Volkswagen",
    "фольксваген": "Volkswagen",
    "фольцваген": "Volkswagen",
    "мерседес": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "toyota": "Toyota",
    "тойота": "Toyota",
    "honda": "Honda",
    "хонда": "Honda",
    "ford": "Ford",
    "форд": "Ford",
    "opel": "Opel",
    "опель": "Opel",
    "renault": "Renault",
    "рено": "Renault",
    "peugeot": "Peugeot",
    "пежо": "Peugeot",
    "citroen": "Citroen",
    "сітроен": "Citroen",
    "ситроен": "Citroen",
    "skoda": "Skoda",
    "шкода": "Skoda",
    "seat": "Seat",
    "сеат": "Seat",
    "nissan": "Nissan",
    "ніссан": "Nissan",
    "ниссан": "Nissan",
    "mazda": "Mazda",
    "мазда": "Mazda",
    "hyundai": "Hyundai",
    "хюндай": "Hyundai",
    "kia": "Kia",
    "кіа": "Kia",
    "киа": "Kia",
    "chevrolet": "Chevrolet",
    "шевроле": "Chevrolet",
    "fiat": "Fiat",
    "фіат": "Fiat",
    "subaru": "Subaru",
    "субару": "Subaru",
    "mitsubishi": "Mitsubishi",
    "міцубісі": "Mitsubishi",
    "мицубиси": "Mitsubishi",
    "tesla": "Tesla",
    "тесла": "Tesla",
    "volvo": "Volvo",
    "вольво": "Volvo",
    "lexus": "Lexus",
    "лексус": "Lexus",
}

CITY_ALIASES = {
    "київ": "Київ",
    "киев": "Київ",
    "kyiv": "Київ",
    "kiev": "Київ",
    "львів": "Львів",
    "львов": "Львів",
    "lviv": "Львів",
    "одеса": "Одеса",
    "одесса": "Одеса",
    "odesa": "Одеса",
    "дніпро": "Дніпро",
    "днепр": "Дніпро",
    "dnipro": "Дніпро",
    "харків": "Харків",
    "харьков": "Харків",
    "kharkiv": "Харків",
    "запоріжжя": "Запоріжжя",
    "запорожье": "Запоріжжя",
    "вінниця": "Вінниця",
    "винница": "Вінниця",
    "івано-франківськ": "Івано-Франківськ",
    "івано франківськ": "Івано-Франківськ",
    "ивано-франковск": "Івано-Франківськ",
    "тернопіль": "Тернопіль",
    "чернівці": "Чернівці",
    "черкасси": "Черкаси",
    "черкаси": "Черкаси",
    "полтава": "Полтава",
    "рівне": "Рівне",
    "ровно": "Рівне",
    "луцьк": "Луцьк",
    "ужгород": "Ужгород",
    "житомир": "Житомир",
    "миколаїв": "Миколаїв",
    "николаев": "Миколаїв",
    "хмельницький": "Хмельницький",
}

PART_KEYWORDS = {
    "акпп": "АКПП",
    "кпп": "КПП",
    "мкпп": "МКПП",
    "коробка": "коробка передач",
    "автомат": "АКПП",
    "автоматична": "АКПП",
    "автоматическая": "АКПП",
    "dsg": "DSG",
    "8hp": "ZF 8HP",
    "двигун": "двигун",
    "двигатель": "двигун",
    "мотор": "двигун",
    "фара": "фара",
    "бампер": "бампер",
    "двері": "двері",
    "дверь": "двері",
    "крило": "крило",
    "капот": "капот",
    "морда": "передня частина",
    "телевізор": "передня панель",
    "телевизор": "передня панель",
    "стартер": "стартер",
    "генератор": "генератор",
    "турбіна": "турбіна",
    "турбина": "турбіна",
    "форсунка": "форсунка",
    "радіатор": "радіатор",
    "радиатор": "радіатор",
    "дзеркало": "дзеркало",
    "зеркало": "дзеркало",
    "підвіска": "підвіска",
    "подвеска": "підвіска",
}

SERVICE_KEYWORDS = {
    "сто": "СТО",
    "сервіс": "автосервіс",
    "сервис": "автосервіс",
    "ремонт": "ремонт",
    "автоелектрик": "автоелектрик",
    "автоэлектрик": "автоелектрик",
    "електрик": "автоелектрик",
    "эвакуатор": "евакуатор",
    "евакуатор": "евакуатор",
    "шиномонтаж": "шиномонтаж",
    "діагностика": "діагностика",
    "диагностика": "діагностика",
    "розвал": "розвал-сходження",
    "сходження": "розвал-сходження",
}

FUEL_KEYWORDS = {
    "дизель": "diesel",
    "diesel": "diesel",
    "бензин": "petrol",
    "газ": "gas",
    "гібрид": "hybrid",
    "гибрид": "hybrid",
    "електро": "electric",
    "electric": "electric",
}

TRANSMISSION_KEYWORDS = {
    "акпп": "automatic",
    "автомат": "automatic",
    "автоматична": "automatic",
    "автоматическая": "automatic",
    "dsg": "DSG",
    "8hp": "ZF 8HP",
    "at": "automatic",
    "кпп": "manual",
    "мкпп": "manual",
    "механіка": "manual",
    "механика": "manual",
}

SIDE_KEYWORDS = {
    "ліва": "left",
    "лівий": "left",
    "левый": "left",
    "левая": "left",
    "правий": "right",
    "права": "right",
    "правый": "right",
    "правая": "right",
    "передня": "front",
    "передний": "front",
    "задня": "rear",
    "задний": "rear",
}

URGENT_WORDS = {"терміново", "срочно", "urgent", "сьогодні", "сегодня", "зараз", "asap"}
LOW_URGENCY_WORDS = {"не терміново", "несрочно", "не срочно", "коли буде", "можна пізніше"}
CAR_WORDS = {"авто", "машина", "автомобіль", "купити авто", "куплю авто"}
SELLER_WORDS = {"продавець", "магазин", "розборка", "авторозборка", "шрот", "разборка", "автошрот", "постачальник"}
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)
MODEL_RE = re.compile(r"\b([a-zа-яіїєґ]{1,4}\d{1,3}|[a-zа-яіїєґ]?\d{1,3}[a-zа-яіїєґ]?)\b", re.IGNORECASE)
ENGINE_RE = re.compile(r"\b\d[.,]\d\s?(?:tdi|tsi|cdi|hdi|dci|jtd|mpi|turbo)?\b", re.IGNORECASE)
ENGINE_CODE_RE = re.compile(r"\b(?:[a-z]{2,4}\d{1,2}|\d{1,2}hp|dsg|n\d{2}|b\d{2}|m\d{2}|cayc|cbbb|cfhc)\b", re.IGNORECASE)
RESTYLE_WORDS = {"рест", "рестайл", "рестайлінг", "рестайлинг", "facelift"}


@dataclass(slots=True)
class InterpretedRequest:
    intent: str = "unknown"
    category: str = "unknown"
    part_name: str | None = None
    service_type: str | None = None
    brand: str | None = None
    model: str | None = None
    generation: str | None = None
    engine: str | None = None
    transmission: str | None = None
    fuel: str | None = None
    body: str | None = None
    side: str | None = None
    city: str | None = None
    vin: str | None = None
    urgency: str = "normal"
    confidence: float = 0.0
    clarification_needed: bool = True
    clarification_question: str | None = "Уточніть, будь ласка, що саме потрібно знайти?"
    normalized_query: str = ""
    search_terms: list[str] = field(default_factory=list)
    source: str = "fallback"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_text(value: Any, max_length: int = 120) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned[:max_length] if cleaned else None


def _clamp_confidence(value: Any, default: float = 0.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(confidence, 1.0))


def normalize_query(raw_text: str | None) -> str:
    text = re.sub(r"\s+", " ", (raw_text or "").strip())
    return text[:MAX_QUERY_LENGTH]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\-\.]+", text.lower(), flags=re.UNICODE)


def _find_alias(text: str, aliases: dict[str, str]) -> str | None:
    padded = f" {text.lower()} "
    for alias, canonical in aliases.items():
        pattern = f" {alias.lower()} "
        if pattern in padded or re.search(rf"\b{re.escape(alias.lower())}\b", text.lower(), re.UNICODE):
            return canonical
    return None


def _find_keyword(tokens: list[str], keywords: dict[str, str]) -> str | None:
    for token in tokens:
        token = token.strip(".,!?;:")
        if token in keywords:
            return keywords[token]
    return None


def _build_search_terms(result: InterpretedRequest) -> list[str]:
    values = [
        result.part_name,
        result.service_type,
        result.brand,
        result.model,
        result.generation,
        result.engine,
        result.transmission,
        result.fuel,
        result.body,
        result.side,
        result.city,
        result.vin,
    ]
    terms: list[str] = []
    for value in values:
        if value and value not in terms:
            terms.append(value)
    if not terms and result.normalized_query:
        terms.append(result.normalized_query)
    return terms[:10]


def _clarification_for(result: InterpretedRequest) -> str | None:
    if result.intent == "unknown":
        return "Уточніть, будь ласка: потрібна запчастина, авто, сервіс чи продавець?"
    if result.category == "parts" and not result.part_name:
        return "Яку саме запчастину потрібно знайти?"
    if result.category == "services" and not result.service_type:
        return "Яка саме послуга потрібна: СТО, автоелектрик, евакуатор, шиномонтаж чи інше?"
    if not result.city:
        return "У якому місті шукати?"
    return None


def normalize_interpretation(payload: dict[str, Any] | None, raw_text: str, source: str = "ai") -> InterpretedRequest:
    payload = payload or {}
    normalized = normalize_query(raw_text)
    result = InterpretedRequest(
        intent=str(payload.get("intent") or "unknown"),
        category=str(payload.get("category") or "unknown"),
        part_name=_clean_text(payload.get("part_name")),
        service_type=_clean_text(payload.get("service_type")),
        brand=_clean_text(payload.get("brand")),
        model=_clean_text(payload.get("model")),
        generation=_clean_text(payload.get("generation")),
        engine=_clean_text(payload.get("engine")),
        transmission=_clean_text(payload.get("transmission")),
        fuel=_clean_text(payload.get("fuel")),
        body=_clean_text(payload.get("body")),
        side=_clean_text(payload.get("side")),
        city=_clean_text(payload.get("city")),
        vin=_clean_text(payload.get("vin"), 32),
        urgency=str(payload.get("urgency") or "normal"),
        confidence=_clamp_confidence(payload.get("confidence"), 0.0),
        clarification_needed=bool(payload.get("clarification_needed", False)),
        clarification_question=_clean_text(payload.get("clarification_question"), 240),
        normalized_query=_clean_text(payload.get("normalized_query"), MAX_QUERY_LENGTH) or normalized,
        search_terms=[],
        source=source,
    )

    if result.intent not in ALLOWED_INTENTS:
        result.intent = "unknown"
    if result.category not in ALLOWED_CATEGORIES:
        result.category = "unknown"
    if result.urgency not in ALLOWED_URGENCY:
        result.urgency = "normal"

    if result.category == "services" and result.intent == "unknown":
        result.intent = "service_search"
    elif result.category == "parts" and result.intent == "unknown":
        result.intent = "parts_search"
    elif result.category == "cars" and result.intent == "unknown":
        result.intent = "car_search"
    elif result.category == "sellers" and result.intent == "unknown":
        result.intent = "seller_search"

    raw_terms = payload.get("search_terms")
    if isinstance(raw_terms, list):
        result.search_terms = [term for term in (_clean_text(item, 80) for item in raw_terms) if term][:10]
    if not result.search_terms:
        result.search_terms = _build_search_terms(result)

    question = _clarification_for(result)
    if question and result.confidence < 0.75:
        result.clarification_needed = True
        result.clarification_question = result.clarification_question or question
    elif not result.clarification_question:
        result.clarification_question = None

    if result.source == "fallback":
        result.confidence = min(result.confidence, 0.65)

    return result


def fallback_parse_request(raw_text: str | None) -> InterpretedRequest:
    normalized = normalize_query(raw_text)
    lowered = normalized.lower()
    tokens = _tokens(normalized)

    result = InterpretedRequest(normalized_query=normalized, source="fallback")
    if not normalized:
        result.confidence = 0.0
        return result

    result.brand = _find_alias(lowered, BRAND_ALIASES)
    result.city = _find_alias(lowered, CITY_ALIASES)
    result.part_name = _find_keyword(tokens, PART_KEYWORDS)
    result.service_type = _find_keyword(tokens, SERVICE_KEYWORDS)
    result.fuel = _find_keyword(tokens, FUEL_KEYWORDS)
    result.transmission = _find_keyword(tokens, TRANSMISSION_KEYWORDS)
    result.side = _find_keyword(tokens, SIDE_KEYWORDS)

    vin_match = VIN_RE.search(normalized.upper())
    if vin_match:
        result.vin = vin_match.group(0).upper()

    engine_match = ENGINE_RE.search(lowered)
    if engine_match:
        result.engine = engine_match.group(0).replace(",", ".").strip()
    else:
        for engine_code_match in ENGINE_CODE_RE.finditer(lowered):
            code = engine_code_match.group(0).lower()
            if code not in BRAND_ALIASES and code not in {"dsg", "8hp"}:
                result.engine = engine_code_match.group(0).upper()
                break

    if any(word in lowered for word in RESTYLE_WORDS):
        result.generation = result.generation or "рестайлінг"

    if any(phrase in lowered for phrase in LOW_URGENCY_WORDS):
        result.urgency = "low"
    elif any(word in lowered for word in URGENT_WORDS):
        result.urgency = "urgent"

    if result.service_type:
        result.intent = "service_search"
        result.category = "services"
    elif result.part_name or result.transmission:
        result.intent = "parts_search"
        result.category = "parts"
        if not result.part_name and result.transmission == "automatic":
            result.part_name = "АКПП"
    elif any(word in lowered for word in SELLER_WORDS):
        result.intent = "seller_search"
        result.category = "sellers"
    elif any(word in lowered for word in CAR_WORDS):
        result.intent = "car_search"
        result.category = "cars"

    # Lightweight model/generation detection after brand token, plus common chassis codes.
    model_candidates = [match.group(1) for match in MODEL_RE.finditer(lowered)]
    for candidate in model_candidates:
        if candidate.lower() not in BRAND_ALIASES and not candidate.isdigit():
            result.model = candidate.upper() if any(char.isdigit() for char in candidate) else candidate.title()
            break

    generation_candidates = [match.group(1).upper() for match in re.finditer(r"\b([cfegw]\d{1,2}|b\d|c\d|a\d|e\d{2}|w\d{3})\b", lowered, re.IGNORECASE)]
    if generation_candidates:
        result.generation = next((candidate for candidate in generation_candidates if candidate != result.model), generation_candidates[-1])
        if not result.model:
            result.model = result.generation

    score = 0.35
    for attr, weight in (
        (result.intent != "unknown", 0.08),
        (bool(result.brand), 0.08),
        (bool(result.model), 0.05),
        (bool(result.part_name or result.service_type), 0.1),
        (bool(result.city), 0.06),
        (bool(result.vin), 0.06),
        (bool(result.fuel or result.engine or result.side), 0.04),
    ):
        if attr:
            score += weight
    result.confidence = min(score, 0.65)
    result.search_terms = _build_search_terms(result)
    result.clarification_question = _clarification_for(result)
    result.clarification_needed = bool(result.clarification_question) or result.confidence < 0.5
    return result


def _system_prompt() -> str:
    fields = [
        "intent", "category", "part_name", "service_type", "brand", "model", "generation",
        "engine", "transmission", "fuel", "body", "side", "city", "vin", "urgency",
        "confidence", "clarification_needed", "clarification_question", "normalized_query", "search_terms",
    ]
    return (
        "You are a strict automotive request interpreter for a Ukrainian marketplace. "
        "Return only one valid JSON object and no prose. Do not answer as a chatbot. "
        f"Required fields: {', '.join(fields)}. "
        "Allowed intent: parts_search, service_search, car_search, seller_search, unknown. "
        "Allowed category: parts, services, cars, sellers, unknown. "
        "Allowed urgency: low, normal, urgent. "
        "Use null for unknown scalar values. search_terms must be an array of concise terms. "
        "Normalize common car brands to Latin canonical names where obvious, cities to Ukrainian names, "
        "and side to left/right/front/rear. Understand Ukrainian/Russian dismantler slang: АКПП, КПП, автомат, коробка, морда, рест/рестайл, шрот, розборка, мотор/двигун, DSG, 8HP, N47, CAYC. Confidence is 0..1."
    )


def _post_openai_json(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=AI_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.warning("AI request interpreter returned HTTP %s: %s", exc.code, body[:180])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("AI request interpreter transport failed: %s", exc.__class__.__name__)
    return None


async def _call_openai(raw_text: str) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("AI_REQUEST_MODEL", DEFAULT_AI_REQUEST_MODEL)
    base_url = os.getenv("OPENAI_BASE_URL", OPENAI_CHAT_COMPLETIONS_URL).rstrip("/")
    url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 450,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": raw_text},
        ],
    }
    data = await asyncio.to_thread(_post_openai_json, url, api_key, payload)
    if not data:
        return None

    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    return _extract_json_object(content)


async def interpret_buyer_request(raw_text: str | None) -> dict[str, Any]:
    """Interpret buyer text into strict JSON-compatible dict with fallback safety."""
    normalized = normalize_query(raw_text)
    if len(normalized) < MIN_AI_QUERY_LENGTH:
        return fallback_parse_request(normalized).to_dict()

    try:
        ai_payload = await asyncio.wait_for(_call_openai(normalized), timeout=AI_TIMEOUT_SECONDS + 1)
        if ai_payload:
            interpreted = normalize_interpretation(ai_payload, normalized, source="ai")
            if interpreted.normalized_query and interpreted.intent in ALLOWED_INTENTS:
                return interpreted.to_dict()
    except Exception as exc:
        logger.warning("AI request interpretation failed; using fallback: %s", exc.__class__.__name__)

    return fallback_parse_request(normalized).to_dict()
