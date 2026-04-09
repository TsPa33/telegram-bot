from aiogram.fsm.state import StatesGroup, State


class AddUser(StatesGroup):
    name = State()
    website = State()
    phone = State()
    brands = State()
    models = State()
