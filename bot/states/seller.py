from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    # авто
    brand = State()
    model = State()
    new_model = State()

    # (залишаємо на майбутнє, не чіпаємо)
    waiting_for_photo = State()

    # реєстрація
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()

    # видалення
    delete_car = State()
