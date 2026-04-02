from aiogram.fsm.state import State, StatesGroup


class SellerStates(StatesGroup):
    waiting_for_brand = State()
    waiting_for_model = State()
