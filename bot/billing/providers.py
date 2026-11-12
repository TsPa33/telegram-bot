"""No LiqPay implementation. Fixture events are not proof of real payment."""

from dataclasses import dataclass
from typing import Protocol
from .models import BillingError


@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    event_id: str
    transaction_id: str
    intent_id: str
    amount_minor: int
    currency: str
    merchant: str
    status: str
    environment: str


class PaymentAdapter(Protocol):
    name: str
    environment: str

    def verify(self, event: ProviderEvent) -> None: ...


class FixtureAdapter:
    """In-process test adapter only; must not be exposed as a public webhook."""

    name = "fixture"
    environment = "test"
    merchant = "disposable-fixture"

    def verify(self, event: ProviderEvent) -> None:
        if (
            event.provider != self.name
            or event.environment != self.environment
            or event.merchant != self.merchant
            or event.status not in {"pending", "success", "failure"}
            or type(event.amount_minor) is not int
            or event.amount_minor <= 0
            or event.currency != "UAH"
            or any(
                not isinstance(v, str) or not 1 <= len(v) <= 160
                for v in (event.event_id, event.transaction_id, event.intent_id)
            )
        ):
            raise BillingError("Invalid fixture event; no real provider is supported")
