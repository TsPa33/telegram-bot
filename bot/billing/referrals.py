"""Sandbox-only first confirmed base-plan reward, versioned policy and compensating entries."""

import secrets
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from .wallet import Wallet
from .service import uid
from .global_core import utcnow
from .models import BillingError, Conflict, Permission


class Referrals:
    def __init__(self, core, *, enabled=False):
        self.core, self.db, self.enabled = core, core.db, enabled
        self.wallet = Wallet(core, enabled=enabled)

    def code(self, actor):
        self.wallet.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            self.wallet.lock(c, actor.account_id)
            c.execute(
                "SELECT code FROM billing.referral_codes WHERE account_id=%s",
                (actor.account_id,),
            )
            row = c.fetchone()
            if row:
                return row["code"]
            code = secrets.token_hex(8).upper()
            c.execute(
                "INSERT INTO billing.referral_codes(account_id,code) VALUES (%s,%s)",
                (actor.account_id, code),
            )
            return code

    def bind(self, actor, code):
        self.wallet.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.MANAGE)
            c.execute("SELECT pg_advisory_xact_lock(48151999)")
            self.wallet.lock(c, actor.account_id)
            c.execute(
                "SELECT r.account_id,a.owner_principal FROM billing.referral_codes r JOIN billing.accounts a ON a.id=r.account_id WHERE r.code=%s",
                (code,),
            )
            ref = c.fetchone()
            c.execute(
                "SELECT owner_principal FROM billing.accounts WHERE id=%s",
                (actor.account_id,),
            )
            owner = c.fetchone()
            if (
                not ref
                or ref["account_id"] == actor.account_id
                or ref["owner_principal"] == owner["owner_principal"]
            ):
                raise BillingError("Self-referral or unknown code")
            c.execute(
                "SELECT * FROM billing.referral_bindings WHERE referred_account=%s",
                (actor.account_id,),
            )
            old = c.fetchone()
            if old:
                if old["referrer_account"] != ref["account_id"]:
                    raise Conflict("Referral attribution is immutable")
                return dict(old)
            c.execute(
                "SELECT 1 FROM billing.settlements s JOIN billing.invoices i ON i.id=s.invoice_id WHERE s.account_id=%s AND i.kind='base' LIMIT 1",
                (actor.account_id,),
            )
            if c.fetchone():
                raise Conflict(
                    "Referral must be attributed before the first confirmed base payment"
                )
            c.execute(
                "WITH RECURSIVE chain AS (SELECT referrer_account FROM billing.referral_bindings WHERE referred_account=%s UNION SELECT b.referrer_account FROM billing.referral_bindings b JOIN chain c ON b.referred_account=c.referrer_account) SELECT 1 FROM chain WHERE referrer_account=%s",
                (ref["account_id"], actor.account_id),
            )
            if c.fetchone():
                raise Conflict("Referral cycle forbidden")
            c.execute("SELECT max(version) AS version FROM billing.referral_policies")
            version = c.fetchone()["version"]
            c.execute(
                "INSERT INTO billing.referral_bindings(referred_account,referrer_account,policy_version) VALUES (%s,%s,%s) RETURNING *",
                (actor.account_id, ref["account_id"], version),
            )
            return dict(c.fetchone())

    def on_settlement(self, c, intent):
        self.wallet.gate()
        c.execute(
            "SELECT s.*,i.kind,i.amount_minor,n.environment,n.provider AS intent_provider FROM billing.settlements s JOIN billing.invoices i ON i.id=s.invoice_id JOIN billing.intents n ON n.id=s.intent_id WHERE s.invoice_id=%s",
            (intent["invoice_id"],),
        )
        s = c.fetchone()
        if (
            not s
            or s["kind"] != "base"
            or s["intent_provider"] != "liqpay"
            or s["environment"] != "sandbox"
        ):
            return
        c.execute(
            "SELECT 1 FROM billing.referral_rewards WHERE referred_account=%s",
            (s["account_id"],),
        )
        if c.fetchone():
            return
        c.execute(
            "SELECT 1 FROM billing.settlements s JOIN billing.invoices i ON i.id=s.invoice_id WHERE s.account_id=%s AND i.kind='base' AND s.id<>%s LIMIT 1",
            (s["account_id"], s["id"]),
        )
        if c.fetchone():
            return
        c.execute(
            "SELECT b.*,p.rate_bps,p.hold_days FROM billing.referral_bindings b JOIN billing.referral_policies p ON p.version=b.policy_version WHERE b.referred_account=%s",
            (s["account_id"],),
        )
        binding = c.fetchone()
        if not binding:
            return
        amount = int(
            (Decimal(s["amount_minor"]) * binding["rate_bps"] / 10000).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        if not amount:
            return
        reward = uid()
        operation = self.wallet.post(
            c,
            binding["referrer_account"],
            "referral:" + reward,
            "referral_reward",
            "referral",
            amount,
            [("marketing_expense", amount), ("referral_pending", -amount)],
        )
        c.execute(
            "INSERT INTO billing.referral_rewards(id,referrer_account,referred_account,settlement_id,policy_version,amount_minor,available_after,wallet_operation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                reward,
                binding["referrer_account"],
                s["account_id"],
                s["id"],
                binding["policy_version"],
                amount,
                utcnow() + timedelta(days=binding["hold_days"]),
                operation,
            ),
        )

    def state(self, c, reward):
        c.execute(
            "SELECT coalesce(sum(amount_minor) FILTER(WHERE kind='reversed'),0) AS reversed,coalesce(sum(amount_minor) FILTER(WHERE kind='available'),0) AS available FROM billing.referral_reward_events WHERE reward_id=%s",
            (reward["id"],),
        )
        return {k: int(v) for k, v in c.fetchone().items()}

    def release(self, reward_id, *, now=None):
        self.wallet.gate()
        stamp = now or utcnow()
        with self.db.transaction() as c:
            c.execute(
                "SELECT * FROM billing.referral_rewards WHERE id=%s FOR UPDATE",
                (reward_id,),
            )
            r = c.fetchone()
            if not r:
                raise BillingError("Unknown reward")
            self.wallet.lock(c, r["referrer_account"])
            state = self.state(c, r)
            if state["available"] or state["reversed"] >= r["amount_minor"]:
                return False
            if r["available_after"] > stamp:
                raise Conflict("Referral hold period is not complete")
            amount = r["amount_minor"] - state["reversed"]
            operation = self.wallet.post(
                c,
                r["referrer_account"],
                "referral-available:" + r["id"],
                "reward_available",
                "referral",
                amount,
                [("referral_pending", amount), ("wallet_referral", -amount)],
                r["wallet_operation_id"],
            )
            c.execute(
                "INSERT INTO billing.referral_reward_events VALUES (%s,%s,'available',%s,%s,%s,now())",
                (uid(), r["id"], amount, "available:" + r["id"], operation),
            )
            return True

    def on_reversal(self, c, settlement):
        self.wallet.gate()
        c.execute(
            "SELECT r.*,i.amount_minor AS paid_minor FROM billing.referral_rewards r JOIN billing.settlements s ON s.id=r.settlement_id JOIN billing.invoices i ON i.id=s.invoice_id WHERE r.settlement_id=%s FOR UPDATE OF r",
            (settlement["id"],),
        )
        r = c.fetchone()
        if not r:
            return
        self.wallet.lock(c, r["referrer_account"])
        state = self.state(c, r)
        c.execute(
            "SELECT coalesce(sum(amount_minor),0) AS total FROM billing.reversals WHERE settlement_id=%s",
            (settlement["id"],),
        )
        total = c.fetchone()["total"]
        target = int(
            (Decimal(r["amount_minor"]) * total / r["paid_minor"]).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        amount = target - state["reversed"]
        if amount <= 0:
            return
        source = "wallet_referral" if state["available"] else "referral_pending"
        operation = self.wallet.post(
            c,
            r["referrer_account"],
            "referral-reverse:" + r["id"] + ":" + str(target),
            "reward_reversal",
            "referral",
            amount,
            [(source, amount), ("marketing_expense", -amount)],
            r["wallet_operation_id"],
        )
        c.execute(
            "INSERT INTO billing.referral_reward_events VALUES (%s,%s,'reversed',%s,%s,%s,now())",
            (
                uid(),
                r["id"],
                amount,
                "reversed:" + r["id"] + ":" + str(target),
                operation,
            ),
        )

    def history(self, actor):
        self.wallet.gate()
        with self.db.transaction() as c:
            self.core.authorize(c, actor, Permission.VIEW)
            c.execute(
                "SELECT * FROM billing.referral_rewards WHERE referrer_account=%s ORDER BY created_at DESC LIMIT 100",
                (actor.account_id,),
            )
            rewards = [dict(r) for r in c.fetchall()]
            for r in rewards:
                state = self.state(c, r)
                r.update(
                    reversed_minor=state["reversed"],
                    state="reversed"
                    if state["reversed"] >= r["amount_minor"]
                    else "available"
                    if state["available"]
                    else "pending",
                )
            return dict(test_only=True, payout_available=False, rewards=rewards)
