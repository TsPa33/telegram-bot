"""Replayable authenticated entitlement delivery; no startup worker or live defaults."""

from datetime import timedelta
import httpx
from .transport import Transport
from .models import BillingError, Permission, Forbidden
from .global_core import utcnow
from .liqpay import _check_url


class EntitlementDelivery:
    def __init__(self, db, peers, *, network_enabled=False, transport=None):
        # peers: trusted binding peer -> {key: bytes, url: HTTPS callback}. Never from an HTTP body.
        self.db, self.peers, self.network_enabled, self.transport = (
            db,
            peers,
            network_enabled,
            transport,
        )
        for name, p in peers.items():
            if len(p["key"]) < 32:
                raise BillingError("Entitlement key required")
            if p.get("url"):
                _check_url(p["url"])

    def _proof(self, row, peer):
        return Transport(
            self.peers[peer]["key"],
            "billing-api",
            peer,
            "entitlements.write",
            environment=self.db.environment,
        ).sign(row["payload"])

    def latest(self, core, actor, binding):
        with self.db.transaction() as c:
            core.authorize(c, actor, Permission.VIEW)
            c.execute(
                "SELECT o.*,l.peer FROM billing.outbox o JOIN billing.subscriptions s ON s.id=o.aggregate_id JOIN billing.product_links l ON l.binding_id=s.binding_id WHERE s.binding_id=%s AND s.account_id=%s ORDER BY o.version DESC LIMIT 1",
                (binding, actor.account_id),
            )
            row = c.fetchone()
            if not row:
                return {"proof": None}
            return {"proof": self._proof(row, row["peer"])}

    def acknowledge(self, proof, *, cursor=None):
        # The receiver signs only after its own projection transaction commits.
        for peer, p in self.peers.items():
            try:
                e = Transport(
                    p["key"],
                    peer,
                    "billing-api",
                    "entitlements.ack",
                    environment=self.db.environment,
                ).verify(proof)
            except BillingError:
                continue
            payload = e["payload"]

            def apply(c):
                c.execute(
                    "SELECT o.id,o.version,o.payload,l.peer FROM billing.outbox o JOIN billing.subscriptions s ON s.id=o.aggregate_id JOIN billing.product_links l ON l.binding_id=s.binding_id WHERE o.id=%s",
                    (payload.get("event_id"),),
                )
                row = c.fetchone()
                if (
                    not row
                    or row["peer"] != peer
                    or payload.get("workspace_id") != row["payload"]["workspace_id"]
                    or payload.get("billing_account_id")
                    != row["payload"]["billing_account_id"]
                    or type(payload.get("version")) is not int
                    or payload["version"] < row["version"]
                ):
                    raise Forbidden("Entitlement acknowledgment scope mismatch")
                c.execute(
                    "UPDATE billing.outbox SET delivered_at=now() WHERE id=%s AND delivered_at IS NULL",
                    (row["id"],),
                )
                return True

            if cursor is not None:
                return apply(cursor)
            with self.db.transaction() as c:
                return apply(c)
        raise Forbidden("Invalid entitlement acknowledgment")

    def run_once(self, *, limit=100):
        if not self.network_enabled:
            return {"delivered": 0, "blocked": "delivery_disabled"}
        if type(limit) is not int or not 1 <= limit <= 100:
            raise BillingError("Bounded delivery batch required")
        delivered = 0
        for _ in range(limit):
            with self.db.transaction() as c:
                c.execute(
                    "INSERT INTO billing.outbox_delivery(outbox_id) SELECT id FROM billing.outbox WHERE delivered_at IS NULL AND topic='billing.entitlement.snapshot.v2' ON CONFLICT DO NOTHING"
                )
                c.execute(
                    "SELECT o.*,l.peer FROM billing.outbox_delivery d JOIN billing.outbox o ON o.id=d.outbox_id JOIN billing.subscriptions s ON s.id=o.aggregate_id JOIN billing.product_links l ON l.binding_id=s.binding_id WHERE o.delivered_at IS NULL AND d.next_attempt_at<=now() ORDER BY o.created_at LIMIT 1 FOR UPDATE OF d SKIP LOCKED"
                )
                row = c.fetchone()
                if not row:
                    break
                c.execute(
                    "UPDATE billing.outbox_delivery SET attempts=attempts+1,next_attempt_at=now()+interval '1 minute' WHERE outbox_id=%s RETURNING attempts",
                    (row["id"],),
                )
                attempt = c.fetchone()["attempts"]
                peer = self.peers.get(row["peer"])
                try:
                    if not peer or not peer.get("url"):
                        raise BillingError("delivery_destination_unconfigured")
                    with httpx.Client(
                        transport=self.transport,
                        timeout=httpx.Timeout(10, connect=3),
                        follow_redirects=False,
                    ) as client:
                        response = client.post(
                            peer["url"], json={"proof": self._proof(row, row["peer"])}
                        )
                    if response.status_code != 200 or len(response.content) > 10000:
                        raise BillingError("delivery_unacknowledged")
                    if not self.acknowledge(response.json()["ack"], cursor=c):
                        raise BillingError("delivery_unacknowledged")
                    delivered += 1
                except (httpx.HTTPError, BillingError, ValueError, KeyError, TypeError):
                    # Fixed error codes only: no body, secret, URL or payer data in logs/storage.
                    c.execute(
                        "UPDATE billing.outbox_delivery SET last_error='delivery_unacknowledged',next_attempt_at=%s WHERE outbox_id=%s",
                        (
                            utcnow()
                            + timedelta(seconds=min(3600, 2 ** min(attempt, 12))),
                            row["id"],
                        ),
                    )
        return {"delivered": delivered}
