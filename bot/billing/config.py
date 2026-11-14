"""Flags document release boundaries; no legacy startup imports this module."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Flags:
    foundation: bool = False
    fixture_adapter: bool = False
    warehouse_enforcement: bool = False
    liqpay: bool = False
    wallet: bool = False
    referrals: bool = False
    payouts: bool = False

    @classmethod
    def from_environment(cls):
        # Only local foundation fixture work can be enabled in this phase.
        return cls(
            foundation=os.getenv("CARPOT_BILLING_FOUNDATION_ENABLED") == "true",
            fixture_adapter=os.getenv("CARPOT_BILLING_FIXTURE_ENABLED") == "true",
        )


def local_billing(dsn: str):
    from .db import Database
    from .models import BillingError
    from .service import Billing

    flags = Flags.from_environment()
    if not flags.foundation or not flags.fixture_adapter:
        raise BillingError(
            "Both local foundation and fixture flags must be explicitly enabled"
        )
    return Billing(Database(dsn, enabled=True))
