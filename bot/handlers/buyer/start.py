from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.states.buyer_states import Buyer


router = Router()


@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)
    print("STATE SET TO Buyer.brand")
    await message.answer("🚗 Обери бренд", reply_markup=brand_kb(brands))
