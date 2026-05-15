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
    # ================= DOMAIN =================
    site_subdomain = State()

    # ================= HEADER =================
    edit_header_title = State()
    edit_about_text = State()

    # ================= SERVICES =================
    site_service_create = State()
    site_service_edit = State()

    # ================= CARS =================
    site_car_create = State()
    site_car_edit = State()

    # ================= CONTACTS =================

    # базові
    site_contact_phone = State()          # (залишаємо для backward)
    site_contact_add_phone = State()      # ➕ новий номер
    site_contact_address = State()
    site_contact_map = State()

    # месенджери
    site_contact_telegram = State()
    site_contact_viber = State()
    site_contact_whatsapp = State()

    # соцмережі
    site_contact_instagram = State()
    site_contact_facebook = State()

    # ================= MEDIA =================
    site_banner = State()
    site_logo = State()
    site_product_photo = State()
    site_service_photo = State()


class SellerCrmStates(StatesGroup):
    crm_slug = State()
    crm_password = State()
