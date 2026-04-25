from aiogram.fsm.state import State, StatesGroup


class ServiceStates(StatesGroup):
    category = State()
    photo = State()
    title = State()
    city = State()
    address = State()
    description = State()
    website = State()
