from aiogram.fsm.state import StatesGroup, State


class Buyer(StatesGroup):
    brand = State()
    model = State()
    garage_vehicle = State()


class BuyerStates(StatesGroup):
    waiting_for_search_query = State()
    request_city = State()
    request_phone = State()
    request_confirm = State()


class AddBrand(StatesGroup):
    waiting_for_brand = State()


class AddModel(StatesGroup):
    waiting_for_model = State()
