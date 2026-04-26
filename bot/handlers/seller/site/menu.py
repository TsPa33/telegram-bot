from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

router = Router()


# TEMP FEATURE FLAG (тільки для тебе)
def site_enabled(user_id: int) -> bool:
    return user_id == 6206952389  # заміни на свій ID


@router.message(F.text == "🌐 Мій сайт")
async def site_menu(message: Message, state: FSMContext):
    if not site_enabled(message.from_user.id):
        return

    await state.clear()
    await state.update_data(flow="seller_site")

    await message.answer(
        "🌐 Мій сайт\n\n"
        "Функціонал у розробці"
    )
