from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


admin_kb = ReplyKeyboardMarkup(
    keyboard=[

        [KeyboardButton(text="📋 Заявки (бренди/моделі)")],
        [KeyboardButton(text="🔐 Верифікація продавців")],

        [KeyboardButton(text="📊 Перегляди")],

        # 🔥 ОСНОВНЕ ДОДАННЯ
        [KeyboardButton(text="👥 Користувачі")],

        # залишаємо старе
        [KeyboardButton(text="➕ Додати користувача")],

    ],
    resize_keyboard=True
)
