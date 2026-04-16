from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.admin_repo import create_verification_request
from bot.states.seller_states import SellerStates

router = Router()


async def check_verified(message: Message, state: FSMContext):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    if seller.get("is_verified"):
        return True

    data = await state.get_data()

    if not data.get("verification_warned"):
        await message.answer(
            "🔐 <b>Акаунт не верифікований</b>\n\n"
            "Щоб користуватись ботом — пройди верифікацію",
            parse_mode="HTML"
        )
        await state.update_data(verification_warned=True)

    return False


@router.message(F.text == "🔐 Верифікація")
async def start_verification(message: Message, state: FSMContext):
    await state.set_state(SellerStates.verification_photo)

    await message.answer(
        "🔐 <b>Верифікація продавця</b>\n\n"
        "📸 Надішли фото паспорта або ID",
        parse_mode="HTML"
    )


@router.message(SellerStates.verification_photo, F.photo)
async def receive_verification_photo(message: Message, state: FSMContext):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    await create_verification_request(
        seller_id=seller["id"],
        photo_id=message.photo[-1].file_id
    )

    await message.answer("✅ Заявка відправлена\n⏳ Очікуй підтвердження")
    await state.clear()


@router.message(SellerStates.verification_photo)
async def verification_error(message: Message):
    await message.answer("❌ Надішли фото документа")
