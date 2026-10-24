import re
from typing import Annotated, Literal
from decimal import Decimal
from pydantic import Field, field_validator, model_validator
from app.schemas import Input, Money

Key = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]
Id = Annotated[str, Field(min_length=1,max_length=36)]
Name = Annotated[str, Field(min_length=1,max_length=200)]
Phone = Annotated[str, Field(min_length=7,max_length=50)]


def normalize_phone(value: str, *, partial=False):
    if not re.fullmatch(r'\+?[0-9() .\-]+', value):
        raise ValueError('Телефон має містити цифри та стандартні розділювачі')
    digits=re.sub(r'\D','',value)
    if digits.startswith('00'):digits=digits[2:]
    # Explicit Ukrainian local form only; never guess a country for other numbers.
    if len(digits)==10 and digits.startswith('0'):digits='38'+digits
    if not (3 if partial else 7)<=len(digits)<=15:raise ValueError('Некоректна довжина телефону')
    return digits


class BuyerInput(Input):
    name: Name
    phone: Phone
    additional_phone: Annotated[str,Field(max_length=50)] = ''
    notes: Annotated[str,Field(max_length=10000)] = ''

    @field_validator('phone','additional_phone')
    @classmethod
    def valid_phone(cls,value):
        if value:normalize_phone(value)
        return value


class OrderLineInput(Input):
    part_id: Id
    quantity: Annotated[int,Field(gt=0,le=1000000)]
    unit_price: Money
    currency: Literal['UAH','USD']

    @field_validator('unit_price')
    @classmethod
    def exact_price(cls,value:Decimal):return value.quantize(Decimal('.01'))


class LinesInput(Input):
    request_key: Key
    lines: Annotated[list[OrderLineInput],Field(min_length=1,max_length=100)]

    @model_validator(mode='after')
    def distinct(self):
        if len({line.part_id for line in self.lines})!=len(self.lines):raise ValueError('Об’єднайте однакові складські позиції в один рядок')
        return self


class Delivery(Input):
    delivery_method: Literal['pickup','branch','address'] = 'pickup'
    city: Annotated[str,Field(max_length=150)] = ''
    delivery_address: Annotated[str,Field(max_length=300)] = ''
    tracking_number: Annotated[str,Field(max_length=100)] = ''
    notes: Annotated[str,Field(max_length=10000)] = ''
    contact_name: Name | None = None
    contact_phone: Phone | None = None

    @field_validator('contact_phone')
    @classmethod
    def valid_phone(cls,value):
        if value:normalize_phone(value)
        return value

    @model_validator(mode='after')
    def delivery_valid(self):
        if self.delivery_method!='pickup' and not(self.city and self.delivery_address):raise ValueError('Для доставки вкажіть місто та відділення або адресу')
        return self


class CreateOrder(LinesInput,Delivery):
    buyer_id: Id


class UpdateOrder(Input):
    request_key: Key
    buyer_id: Id | None = None
    contact_name: Name | None = None
    contact_phone: Phone | None = None
    delivery_method: Literal['pickup','branch','address'] | None = None
    city: Annotated[str,Field(max_length=150)] | None = None
    delivery_address: Annotated[str,Field(max_length=300)] | None = None
    tracking_number: Annotated[str,Field(max_length=100)] | None = None
    notes: Annotated[str,Field(max_length=10000)] | None = None

    @field_validator('contact_phone')
    @classmethod
    def valid_phone(cls,value):
        if value:normalize_phone(value)
        return value

    @model_validator(mode='after')
    def no_null(self):
        if any(getattr(self,key) is None for key in self.model_fields_set):raise ValueError('Не передавайте null; використовуйте порожній рядок для необов’язкових полів')
        return self


class OrderAction(Input):
    request_key: Key


class OrderStatus(OrderAction):
    status: Literal['new','reserved','shipped','completed','cancelled']
