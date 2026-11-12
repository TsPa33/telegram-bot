"""Provider-neutral value objects. Monetary values are integer UAH kopecks."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import FrozenSet


class Permission(str, Enum):
    VIEW = "billing.view"
    MANAGE = "billing.manage"
    SPEND = "wallet.spend"
    REFERRALS = "referrals.view"
    PAYOUT = "payouts.request"


@dataclass(frozen=True)
class Actor:
    """Trusted server identity; never deserialize permissions from a request body."""

    principal_id: str
    account_id: str
    permissions: FrozenSet[Permission]


@dataclass(frozen=True)
class PlanVersion:
    sku: str
    version: int
    product: str
    amount_minor: int
    vehicle_capacity: int
    employees: int
    kind: str = "base"
    currency: str = "UAH"


@dataclass(frozen=True)
class Quote:
    sku: str
    version: int
    quantity: int
    full_amount_minor: int
    payable_minor: int
    currency: str
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class VerifiedBinding:
    """Only a trusted linking verifier may construct this evidence in a future API."""

    workspace_id: str
    product: str
    evidence_id: str
    verified_by: str


class BillingError(ValueError):
    pass


class Forbidden(BillingError):
    pass


class Conflict(BillingError):
    pass
