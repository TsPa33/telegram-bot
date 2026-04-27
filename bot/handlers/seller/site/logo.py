from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "site:edit:logo")
async def set_logo(callback: CallbackQuery, state: FSMContext):
    await state.set_state("site_logo")
    await callback.message.answer("Надішліть логотип")
    await callback.answer()
