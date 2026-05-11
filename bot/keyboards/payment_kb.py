from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.site_packages import format_site_package_title


def payment_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚗 Тарифи гаража",
                    callback_data="pay:garage"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🌐 {format_site_package_title('standard')}",
                    callback_data="pay:site"
                )
            ]
        ]
    )


def garage_tariffs_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 авто — 99 грн",
                    callback_data="pay:garage:99"
                )
            ],
            [
                InlineKeyboardButton(
                    text="5 авто — 199 грн",
                    callback_data="pay:garage:199"
                )
            ],
            [
                InlineKeyboardButton(
                    text="10 авто — 299 грн",
                    callback_data="pay:garage:299"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="pay:back"
                )
            ]
        ]
    )
