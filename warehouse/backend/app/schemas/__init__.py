from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Text100 = Annotated[str, Field(min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Input):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("email")
    @classmethod
    def email_valid(cls, v):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v):
            raise ValueError("Некоректна електронна пошта")
        return v.lower()

    @field_validator("password", mode="before")
    @classmethod
    def preserve_password(cls, v):
        # Passwords must not silently lose leading/trailing whitespace.
        if isinstance(v, str) and v != v.strip():
            raise ValueError("Пароль не повинен починатися чи закінчуватися пробілами")
        return v


class Registration(Credentials):
    name: Annotated[str, Field(min_length=1, max_length=120)]


class VehicleInput(Input):
    manufacturer: Text100
    model: Text100
    generation: Annotated[str, Field(max_length=100)] = ""
    year: Annotated[int, Field(ge=1886, le=2100)]
    engine: Annotated[str, Field(max_length=100)] = ""
    fuel_type: Annotated[str, Field(max_length=50)] = ""
    transmission: Annotated[str, Field(max_length=50)] = ""
    vin: Annotated[str, Field(pattern=r"^[A-HJ-NPR-Z0-9]{17}$")] | None = None
    donor_id: Annotated[str, Field(min_length=1, max_length=80)]
    acquisition_cost: Money | None = None
    acquisition_date: date
    notes: Annotated[str, Field(max_length=10000)] = ""
    status: Literal["planned", "dismantling", "completed"] = "dismantling"


class CategoryNode(Input):
    key: Annotated[str, Field(min_length=1, max_length=200)]
    parent_key: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)]
    kind: Literal["category", "subcategory", "part"]


class CategoryImport(Input):
    source: Text100
    nodes: Annotated[list[CategoryNode], Field(min_length=1, max_length=10000)]


class PartInput(Input):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    category_id: str | None = None
    subcategory_id: str | None = None
    vehicle_id: str | None = None
    oem_number: Annotated[str, Field(max_length=150)] = ""
    article_number: Annotated[str, Field(max_length=150)] = ""
    condition: Literal["used", "new", "damaged", "refurbished"] = "used"
    unit_cost: Money | None = None
    selling_price: Money | None = None
    location: Annotated[str, Field(max_length=120)] = ""
    compatibility_notes: Annotated[str, Field(max_length=10000)] = ""
    description: Annotated[str, Field(max_length=10000)] = ""
    internal_notes: Annotated[str, Field(max_length=10000)] = ""
    availability: Literal["unchecked", "present", "absent", "damaged"] = "unchecked"
    individually_tracked: bool = False
    serial_number: Annotated[str, Field(min_length=1, max_length=120)] | None = None

    @model_validator(mode="after")
    def serial_required(self):
        if self.individually_tracked and not self.serial_number:
            raise ValueError("Для індивідуального обліку потрібен серійний номер")
        return self


class StockInput(Input):
    type: Literal[
        "receipt", "write_off", "reserve", "release", "correction", "transfer"
    ]
    quantity: Annotated[int, Field(ge=0, le=1000000)] = 0
    location: Annotated[str, Field(max_length=120)] | None = None
    reason: Annotated[str, Field(min_length=3, max_length=2000)]

    @model_validator(mode="after")
    def operation_valid(self):
        if (
            self.type in ("receipt", "write_off", "reserve", "release")
            and self.quantity == 0
        ):
            raise ValueError("Кількість має бути більшою за нуль")
        if self.type == "transfer" and not self.location:
            raise ValueError("Вкажіть нове місце зберігання")
        return self


class BulkInput(Input):
    ids: Annotated[list[str], Field(min_length=1, max_length=100)]
    action: Literal["archive", "restore", "transfer"]
    location: Annotated[str, Field(max_length=120)] | None = None
    reason: Annotated[str, Field(min_length=3, max_length=2000)]
