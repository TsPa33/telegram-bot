from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def contact_button(seller_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📞 Написати продавцю",
                    callback_data=f"contact_{seller_id}"
                )
            ]
        ]
    )
