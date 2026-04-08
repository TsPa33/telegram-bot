from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    # авто
    waiting_for_brand = State()
    waiting_for_model = State()
    waiting_for_photo = State()  # ← ОСЬ ЦЕ ГОЛОВНЕ

    # реєстрація
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()

    # видалення
    delete_car = State()
