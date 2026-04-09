from aiogram.fsm.state import StatesGroup, State


class Buyer(StatesGroup):
    brand = State()
    model = State()
