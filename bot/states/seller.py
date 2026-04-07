from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    # 🔹 додавання авто
    waiting_for_brand = State()
    waiting_for_model = State()

    # 🔹 реєстрація продавця
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()
