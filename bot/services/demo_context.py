from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User

from bot.database.repositories.seller_repo import get_or_create_seller, get_seller_by_id

DEMO_CONTEXT_KEYS = ("demo_mode", "demo_seller_id", "demo_site_id", "demo_subdomain")


async def set_demo_context(
    state: FSMContext,
    *,
    seller_id: int,
    site_id: int,
    subdomain: str,
) -> None:
    await state.update_data(
        demo_mode=True,
        demo_seller_id=seller_id,
        demo_site_id=site_id,
        demo_subdomain=subdomain,
        flow="seller_site",
    )


async def clear_demo_context(state: FSMContext) -> None:
    data = await state.get_data()
    for key in (*DEMO_CONTEXT_KEYS, "flow"):
        data.pop(key, None)

    await state.clear()
    if data:
        await state.update_data(**data)


async def get_demo_context(state: FSMContext) -> dict:
    data = await state.get_data()
    if not data.get("demo_mode"):
        return {}

    return {
        "demo_mode": True,
        "demo_seller_id": data.get("demo_seller_id"),
        "demo_site_id": data.get("demo_site_id"),
        "demo_subdomain": data.get("demo_subdomain"),
    }


async def is_demo_mode(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get("demo_mode") and data.get("demo_seller_id"))


async def clear_preserving_demo_context(state: FSMContext) -> None:
    data = await state.get_data()
    demo_data = {
        key: data[key]
        for key in DEMO_CONTEXT_KEYS
        if key in data
    }

    await state.clear()

    if demo_data:
        demo_data["flow"] = "seller_site"
        await state.update_data(**demo_data)


async def resolve_active_seller(message_or_callback: Message | CallbackQuery, state: FSMContext) -> dict | None:
    data = await state.get_data()

    if data.get("demo_mode") and data.get("demo_seller_id"):
        return await get_seller_by_id(int(data["demo_seller_id"]))

    user = _extract_user(message_or_callback)
    if not user:
        return None

    return await get_or_create_seller(
        telegram_id=user.id,
        username=user.username,
    )


async def resolve_active_seller_from_user(user: User, state: FSMContext) -> dict | None:
    data = await state.get_data()

    if data.get("demo_mode") and data.get("demo_seller_id"):
        return await get_seller_by_id(int(data["demo_seller_id"]))

    return await get_or_create_seller(
        telegram_id=user.id,
        username=user.username,
    )


def _extract_user(message_or_callback: Message | CallbackQuery) -> User | None:
    return getattr(message_or_callback, "from_user", None)
