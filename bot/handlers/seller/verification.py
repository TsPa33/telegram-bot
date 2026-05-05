from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.services.verification_service import submit_verification
from bot.keyboards.admin_inline import verification_request_kb
from bot.config import ADMIN_IDS
from bot.states.seller_states import SellerStates

router = Router()


# ================= CHECK VERIFIED =================

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


# ================= START =================

@router.message(F.text == "🔐 Верифікація")
async def start_verification(message: Message, state: FSMContext):
    await state.set_state(SellerStates.verification_passport)

    await message.answer(
        "🔐 <b>Верифікація продавця</b>\n\n"
        "📸 Надішли фото паспорта або ID\n\n"
        "⚠️ Дані використовуються лише для перевірки",
        parse_mode="HTML"
    )


# ================= RECEIVE PHOTO =================

@router.message(SellerStates.verification_passport, F.photo)
async def receive_verification_photo(message: Message, state: FSMContext):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    try:
        request_id = await submit_verification(
            seller=seller,
            photo_id=message.photo[-1].file_id
        )
    except ValueError:
        await message.answer("✅ Ви вже верифіковані")
        await state.clear()
        return

    # 🔥 повідомлення всім адмінам
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=(
                    "🔐 <b>Нова заявка на верифікацію</b>\n\n"
                    f"👤 ID: {message.from_user.id}\n"
                    f"📛 @{message.from_user.username or '—'}"
                ),
                parse_mode="HTML",
                reply_markup=verification_request_kb(request_id)
            )
        except Exception as e:
            print(f"ADMIN SEND ERROR: {e}")

    await message.answer(
        "✅ Заявка відправлена\n"
        "⏳ Очікуй підтвердження адміністратора"
    )

    await state.clear()


# ================= ERROR =================

@router.message(SellerStates.verification_passport)
async def verification_error(message: Message):
    await message.answer("❌ Надішли фото документа")
