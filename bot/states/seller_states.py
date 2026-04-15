from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    # ================= АВТО =================
    brand = State()
    model = State()
    new_model = State()
    new_brand = State()
    photo = State()
    description = State()

    # ================= LEGACY =================
    waiting_for_photo = State()

    # ================= РЕЄСТРАЦІЯ =================
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()

    # ================= ВИДАЛЕННЯ =================
    delete_car = State()

    # ================= PROFILE =================
    edit_profile = State()

    # ================= 🔐 ВЕРИФІКАЦІЯ =================
    verification_passport = State()
