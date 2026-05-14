from aiogram.fsm.state import StatesGroup, State


class Buyer(StatesGroup):
    brand = State()
    model = State()
    garage_vehicle = State()


class AddBrand(StatesGroup):
    waiting_for_brand = State()


class AddModel(StatesGroup):
    waiting_for_model = State()
