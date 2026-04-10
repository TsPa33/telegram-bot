from aiogram.fsm.state import StatesGroup, State


class SellerStates(StatesGroup):
    brand = State()
    model = State()
    new_model = State()
