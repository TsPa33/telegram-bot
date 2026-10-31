"""Contract checks for R11.4.4 donor profile (no database mutation)."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas import VehicleSpecificationsInput
from app.permissions import route_permissions
from app.route_registry import KNOWN_ROUTES


def test_engine_attributes_are_independent():
    data = VehicleSpecificationsInput.model_validate({
        "fuel_type": "Дизель",
        "engine_displacement_l": 2.0,
        "engine_variant": "D5",
        "engine_code": "D4204T23",
        "transmission": "Автомат",
        "drive_type": "AWD",
    })
    assert data.engine_displacement_l == Decimal("2.0")
    assert data.engine_variant == "D5"
    assert data.drive_type == "AWD"


@pytest.mark.parametrize("data", [
    {"engine_displacement_l": 0},
    {"engine_displacement_l": 13},
    {"drive_type": "UNKNOWN"},
    {"engine_code": "A"*81},
    {},
])
def test_invalid_donor_specifications_fail_closed(data):
    with pytest.raises(ValidationError):
        VehicleSpecificationsInput.model_validate(data)


@pytest.mark.parametrize("method,path,permission", [
    ("PATCH", "/api/v1/vehicles/{id}/specifications", "vehicles.edit"),
    ("GET", "/api/v1/vehicles/{id}/photos", "vehicles.view"),
    ("POST", "/api/v1/vehicles/{id}/photos", "vehicles.edit"),
    ("DELETE", "/api/v1/vehicles/{id}/photos/{photo_id}", "vehicles.edit"),
    ("GET", "/api/v1/vehicle-photos/{photo_id}", "vehicles.view"),
])
def test_donor_routes_registered_and_protected(method,path,permission):
    assert (method,path) in KNOWN_ROUTES
    assert permission in route_permissions(method,path,{})
