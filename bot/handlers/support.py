from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup

from bot.database.repositories.support_repo import (
    add_support_message,
    assign_ticket,
    close_ticket,
    create_support_ticket,
    get_ticket,
    get_user_open_ticket,
)
from bot.keyboards.admin_inline import support_ticket_actions_kb
from bot.keyboards.main_menu import main_menu_kb
from bot.services.roles import is_admin
from bot.services.support_notifications import admin_display, notify_support_admins, notify_support_user
from bot.states.admin_states import SupportStates

router = Router()
SUPPORT_BUTTON_TEXT = "💬 Підтримка"
CANCEL_TEXT = "❌ Скасувати"


def support_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _full_name(user) -> str:
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip()


def _ticket_user_line(ticket) -> str:
    username = f"@{ticket['username']}" if ticket.get("username") else "—"
    full_name = ticket.get("full_name") or "—"
    return f"{username}\n{full_name}\nID: {ticket['telegram_id']}"


def _new_ticket_admin_text(ticket, message_text: str) -> str:
    return (
        f"💬 Новий запит підтримки #{ticket['id']}\n\n"
        "Користувач:\n"
        f"{_ticket_user_line(ticket)}\n\n"
        "Повідомлення:\n"
        f"\"{message_text}\""
    )


@router.callback_query(F.data == "support:open")
async def open_support_from_inline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _open_support(callback.message, state, callback.from_user)


@router.message(F.text == SUPPORT_BUTTON_TEXT)
async def open_support_from_reply(message: Message, state: FSMContext):
    await _open_support(message, state, message.from_user)


async def _open_support(message: Message, state: FSMContext, user):
    await state.clear()

    existing_ticket = await get_user_open_ticket(user.id)
    if existing_ticket:
        await message.answer(
            "У вас вже є активний запит підтримки.\n\n"
            f"Ticket:\n#{existing_ticket['id']}"
        )
        return

    await state.set_state(SupportStates.waiting_support_message)
    await message.answer(
        "💬 Підтримка\n\n"
        "Опишіть ваше питання одним повідомленням.\n\n"
        "Менеджер CarPot отримає звернення та спокійно допоможе у чаті.",
        reply_markup=support_cancel_kb(),
    )


@router.message(SupportStates.waiting_support_message, F.text == CANCEL_TEXT)
async def cancel_support_request(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Запит до служби підтримки скасовано.",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


@router.message(SupportStates.waiting_support_message)
async def create_support_request(message: Message, state: FSMContext):
    text = (message.text or message.caption or "").strip()
    if not text:
        await message.answer("Будь ласка, надішліть текстове повідомлення для служби підтримки.")
        return

    existing_ticket = await get_user_open_ticket(message.from_user.id)
    if existing_ticket:
        await state.clear()
        await message.answer(
            "У вас вже є активний запит підтримки.\n\n"
            f"Ticket:\n#{existing_ticket['id']}",
            reply_markup=await main_menu_kb(message.from_user.id),
        )
        return

    ticket = await create_support_ticket(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=_full_name(message.from_user),
        message_text=text,
        subject=text[:120],
    )

    await notify_support_admins(
        message.bot,
        _new_ticket_admin_text(ticket, text),
        reply_markup=support_ticket_actions_kb(ticket["id"]),
    )

    await state.clear()
    await message.answer(
        "✅ Ваш запит передано в службу підтримки.\n\n"
        "Наш менеджер звʼяжеться з вами найближчим часом.\n\n"
        f"Ticket number:\n#{ticket['id']}",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


@router.callback_query(F.data.startswith("support:claim:"))
async def claim_support_ticket(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[-1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Запит не знайдено", show_alert=True)
        return
    if ticket["status"] == "closed":
        await callback.answer("Запит вже закрито", show_alert=True)
        return

    updated = await assign_ticket(
        ticket_id,
        admin_telegram_id=callback.from_user.id,
        assigned_by=callback.from_user.id,
    )
    await callback.answer("Запит взято в роботу")

    await notify_support_admins(
        callback.bot,
        f"👤 Адмін {admin_display(callback.from_user)} взяв у роботу запит #{updated['id']}",
        reply_markup=support_ticket_actions_kb(updated["id"]),
    )


@router.callback_query(F.data.startswith("support:reply:"))
async def start_admin_support_reply(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[-1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await callback.answer("Запит не знайдено", show_alert=True)
        return
    if ticket["status"] == "closed":
        await callback.answer("Запит вже закрито", show_alert=True)
        return

    await state.set_state(SupportStates.waiting_admin_support_reply)
    await state.update_data(support_ticket_id=ticket_id)
    await callback.message.answer(
        f"💬 Відповідь на запит #{ticket_id}\n\n"
        "Надішліть одне повідомлення для користувача або натисніть ❌ Скасувати.",
        reply_markup=support_cancel_kb(),
    )
    await callback.answer()


@router.message(SupportStates.waiting_admin_support_reply, F.text == CANCEL_TEXT)
async def cancel_admin_support_reply(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Відповідь скасовано.")


@router.message(SupportStates.waiting_admin_support_reply)
async def send_admin_support_reply(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Немає доступу")
        return

    data = await state.get_data()
    ticket_id = data.get("support_ticket_id")
    text = (message.text or message.caption or "").strip()

    if not ticket_id:
        await state.clear()
        await message.answer("Не знайдено активний запит для відповіді.")
        return
    if not text:
        await message.answer("Будь ласка, надішліть текст відповіді.")
        return

    ticket = await get_ticket(int(ticket_id))
    if not ticket or ticket["status"] == "closed":
        await state.clear()
        await message.answer("Запит не знайдено або вже закрито.")
        return

    await add_support_message(ticket["id"], "admin", message.from_user.id, text)
    await notify_support_user(
        message.bot,
        ticket["telegram_id"],
        "💬 Відповідь служби підтримки CarPot:\n\n" f"{text}",
    )

    await state.clear()
    await message.answer(f"✅ Відповідь на запит #{ticket['id']} надіслано.")


@router.callback_query(F.data.startswith("support:close:"))
async def close_support_ticket(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    ticket_id = int(callback.data.split(":")[-1])
    ticket = await close_ticket(ticket_id)
    if not ticket:
        await callback.answer("Запит не знайдено", show_alert=True)
        return

    await add_support_message(
        ticket_id,
        "system",
        callback.from_user.id,
        f"Ticket closed by {admin_display(callback.from_user)}",
    )
    await notify_support_admins(
        callback.bot,
        f"🔒 Запит підтримки #{ticket_id} закрито адміном {admin_display(callback.from_user)}",
    )
    await notify_support_user(
        callback.bot,
        ticket["telegram_id"],
        "✅ Ваш запит підтримки закрито.",
    )
    await callback.answer("Запит закрито")
