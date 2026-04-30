from aiogram.fsm.state import State, StatesGroup


class SellerStates(StatesGroup):
    brand = State()
    model = State()
    new_model = State()
    new_brand = State()
    photo = State()
    description = State()
    add_brand = State()
    add_model = State()
    reg_name = State()
    reg_company = State()
    reg_phone = State()
    reg_link = State()
    reg_city = State()
    edit_profile = State()
    delete_car = State()
    verification_passport = State()


class SellerSiteStates(StatesGroup):
    edit_header_title = State()
    edit_about_text = State()
    site_banner = State()
    site_logo = State()
    site_car_create = State()
    site_car_edit = State()
    site_contact_phone = State()
    site_contact_address = State()
    site_contact_map = State()


class ServiceStates(StatesGroup):
    # buyer flow
    city = State()
    category = State()

    # seller create flow
    photo = State()
    title = State()
    address = State()
    description = State()
    website = State()

    # seller edit flow
    edit_value = State()
