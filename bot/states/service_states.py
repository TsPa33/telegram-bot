from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    # ================= АВТО =================
    brand = State()
    model = State()
    new_model = State()
    new_brand = State()
    photo = State()
    description = State()
    add_brand = State()
    add_model = State()

    # ================= РЕЄСТРАЦІЯ =================
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()

    # ================= PROFILE =================
    edit_profile = State()

    # ================= ВИДАЛЕННЯ =================
    delete_car = State()

    # ================= 🔐 ВЕРИФІКАЦІЯ =================
    verification_passport = State()


class SellerSiteStates(StatesGroup):
    # ===== EXISTING =====
    edit_header_title = State()
    edit_about_text = State()

    # ===== MEDIA =====
    site_banner = State()
    site_logo = State()

    # ===== SERVICES =====
    site_service_create = State()
    site_service_edit = State()

    # ===== CARS =====
    site_car_create = State()
    site_car_edit = State()

    # ===== CONTACTS =====
    site_contact_phone = State()
    site_contact_address = State()
    site_contact_map = State()


# 🔥 FIX: BACKWARD COMPATIBILITY
class ServiceStates(StatesGroup):
    """
    Legacy compatibility for old handlers.
    Do NOT use in new code.
    """
    dummy = State()
