"""Sandbox-only ledger preparation. No real topups, transfers, payouts or service activation."""

from .models import BillingError, Conflict, Permission
from .service import uid, fingerprint

BUCKETS = {"cash", "promo", "referral"}


class Wallet:
    def __init__(self, core, *, enabled=False):
        self.core, self.db, self.enabled = core, core.db, enabled

    def gate(self):
        if not self.enabled or self.db.environment != "sandbox":
            raise BillingError(
                "Wallet is test-only pending legal and provider approval"
            )

    def lock(self, c, account):
        self.gate()
        c.execute("SELECT id FROM billing.accounts WHERE id=%s FOR UPDATE", (account,))
        if not c.fetchone():
            raise BillingError("Unknown wallet account")

    @staticmethod
    def balances(c, account):
        c.execute(
            "SELECT ledger_account,-sum(amount_minor) AS balance FROM billing.journal_entries WHERE account_id=%s AND (ledger_account LIKE 'wallet_%%' OR ledger_account='referral_pending') GROUP BY ledger_account",
            (account,),
        )
        values = {r["ledger_account"]: int(r["balance"]) for r in c.fetchall()}
        return {
            b: dict(
                available_minor=values.get("wallet_" + b, 0),
                reserved_minor=values.get("wallet_" + b + "_reserved", 0),
                pending_minor=values.get("referral_pending", 0)
                if b == "referral"
                else 0,
            )
            for b in sorted(BUCKETS)
        }

    def view(self, actor):
        self.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.VIEW)
            c.execute(
                "SELECT id,kind,bucket,amount_minor,created_at FROM billing.wallet_operations WHERE account_id=%s ORDER BY created_at DESC,id LIMIT 100",
                (actor.account_id,),
            )
            history = [dict(r) for r in c.fetchall()]
            return dict(
                test_only=True,
                real_operations_available=False,
                payout_available=False,
                currency="UAH",
                balances=self.balances(c, actor.account_id),
                history=history,
            )

    def post(self, c, account, key, kind, bucket, amount, entries, parent=None):
        self.lock(c, account)
        if (
            bucket not in BUCKETS
            or type(amount) is not int
            or not 0 < amount <= 9_000_000_000_000_000
            or not isinstance(key, str)
            or not 1 <= len(key) <= 160
        ):
            raise BillingError("Invalid wallet command")
        digest = fingerprint([kind, bucket, amount, parent, entries])
        c.execute(
            "SELECT * FROM billing.wallet_operations WHERE account_id=%s AND request_key=%s",
            (account, key),
        )
        old = c.fetchone()
        if old:
            if old["request_hash"] != digest:
                raise Conflict("Wallet command conflict")
            return old["id"]
        if sum(v for _, v in entries) != 0 or len(entries) < 2:
            raise BillingError("Balanced wallet posting required")
        journal, operation = uid(), uid()
        c.execute(
            "INSERT INTO billing.journal_transactions(id,account_id,external_key,currency) VALUES (%s,%s,%s,'UAH')",
            (journal, account, "test-wallet:" + account + ":" + key),
        )
        for ledger, value in entries:
            if value:
                c.execute(
                    "INSERT INTO billing.journal_entries VALUES (%s,%s,%s,%s,%s)",
                    (uid(), journal, account, ledger, value),
                )
        c.execute(
            "INSERT INTO billing.wallet_operations(id,account_id,request_key,request_hash,kind,bucket,amount_minor,parent_id,journal_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (operation, account, key, digest, kind, bucket, amount, parent, journal),
        )
        return operation

    def test_credit(self, actor, amount, key, *, bucket="cash"):
        self.gate()
        if bucket not in {"cash", "promo"}:
            raise BillingError("Referral rewards require confirmed base settlement")
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            return self.post(
                c,
                actor.account_id,
                key,
                "topup" if bucket == "cash" else "bonus_reward",
                bucket,
                amount,
                [("test_funding", amount), ("wallet_" + bucket, -amount)],
            )

    def reserve(self, actor, amount, key, *, bucket="cash"):
        self.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            self.lock(c, actor.account_id)
            c.execute(
                "SELECT id FROM billing.wallet_operations WHERE account_id=%s AND request_key=%s",
                (actor.account_id, key),
            )
            old = c.fetchone()
            if not old and (
                bucket not in BUCKETS
                or type(amount) is not int
                or amount <= 0
                or self.balances(c, actor.account_id)[bucket]["available_minor"]
                < amount
            ):
                raise Conflict("Insufficient test wallet funds")
            return self.post(
                c,
                actor.account_id,
                key,
                "reservation",
                bucket,
                amount,
                [
                    ("wallet_" + bucket, amount),
                    ("wallet_" + bucket + "_reserved", -amount),
                ],
            )

    def finish(self, actor, reservation, amount, key, *, release=False):
        self.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            self.lock(c, actor.account_id)
            c.execute(
                "SELECT * FROM billing.wallet_operations WHERE id=%s AND account_id=%s AND kind='reservation'",
                (reservation, actor.account_id),
            )
            parent = c.fetchone()
            if not parent:
                raise BillingError("Owned reservation required")
            c.execute(
                "SELECT coalesce(sum(amount_minor),0) AS used FROM billing.wallet_operations WHERE parent_id=%s AND kind IN ('capture','release') AND request_key<>%s",
                (reservation, key),
            )
            used = c.fetchone()["used"]
            if (
                type(amount) is not int
                or amount <= 0
                or used + amount > parent["amount_minor"]
            ):
                raise Conflict("Reservation exceeded")
            bucket = parent["bucket"]
            return self.post(
                c,
                actor.account_id,
                key,
                "release" if release else "capture",
                bucket,
                amount,
                [
                    ("wallet_" + bucket + "_reserved", amount),
                    ("wallet_" + bucket if release else "service_obligation", -amount),
                ],
                reservation,
            )

    def refund(self, actor, capture, amount, key):
        self.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            self.lock(c, actor.account_id)
            c.execute(
                "SELECT * FROM billing.wallet_operations WHERE id=%s AND account_id=%s AND kind='capture'",
                (capture, actor.account_id),
            )
            parent = c.fetchone()
            if not parent:
                raise BillingError("Owned capture required")
            c.execute(
                "SELECT coalesce(sum(amount_minor),0) AS used FROM billing.wallet_operations WHERE parent_id=%s AND kind='refund' AND request_key<>%s",
                (capture, key),
            )
            if (
                type(amount) is not int
                or amount <= 0
                or c.fetchone()["used"] + amount > parent["amount_minor"]
            ):
                raise Conflict("Refund exceeds capture")
            return self.post(
                c,
                actor.account_id,
                key,
                "refund",
                parent["bucket"],
                amount,
                [
                    ("service_obligation", amount),
                    ("wallet_" + parent["bucket"], -amount),
                ],
                capture,
            )

    def reverse_credit(self, actor, credit, amount, key):
        self.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            self.lock(c, actor.account_id)
            c.execute(
                "SELECT * FROM billing.wallet_operations WHERE id=%s AND account_id=%s AND kind IN ('topup','bonus_reward')",
                (credit, actor.account_id),
            )
            parent = c.fetchone()
            if not parent:
                raise BillingError("Test credit required")
            c.execute(
                "SELECT coalesce(sum(amount_minor),0) AS used FROM billing.wallet_operations WHERE parent_id=%s AND kind='reversal' AND request_key<>%s",
                (credit, key),
            )
            if (
                type(amount) is not int
                or amount <= 0
                or c.fetchone()["used"] + amount > parent["amount_minor"]
            ):
                raise Conflict("Credit reversal exceeded")
            return self.post(
                c,
                actor.account_id,
                key,
                "reversal",
                parent["bucket"],
                amount,
                [("wallet_" + parent["bucket"], amount), ("test_funding", -amount)],
                credit,
            )

    def payout(self, *args, **kwargs):
        raise BillingError(
            "Payouts and transfers require separate legal/provider approval"
        )
