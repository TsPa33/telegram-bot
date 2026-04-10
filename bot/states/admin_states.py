from aiogram.fsm.state import StatesGroup, State


class AddUser(StatesGroup):
    name = State()
    website = State()
    phone = State()
    models = State()


class EditBrand(StatesGroup):
    waiting_for_new_brand = State()


class EditModel(StatesGroup):
    waiting_for_new_model = State()
