from aiogram.utils.keyboard import InlineKeyboardBuilder


def role_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Продавець", callback_data="role:seller")
    kb.button(text="Покупець", callback_data="role:buyer")
    kb.adjust(2)
    return kb.as_markup()
