# Business contract v1

This records the owner's Phase 1 draft, not authorization to enforce on live users.
All service business policies below are PROPOSED until separately approved. Prices
are seeded as immutable local fixture version 1; no actual product access is changed.

| SKU | Monthly UAH | Active donor capacity | Employees excluding owner |
|---|---:|---:|---:|
| warehouse.standard | 1000 | 10 | 5 |
| warehouse.premium | 4500 | 50 | 10 |
| warehouse.slots.1 | 300 | +1 | 0 |
| warehouse.slots.5 | 1200 | +5 | 0 |
| warehouse.slots.10 | 2000 | +10 | 0 |

Garage capacity is continuous, not a monthly dismantling allowance and never accumulates
on renewal. Existing Warehouse dismantling credits are not capacity grants and must not
be automatically converted without an inventory/financial review.

PROPOSED add-ons: monthly, prorated to base period end, then renewed together. Upgrade
uses credit for unused existing base/add-on allocation; no double billing for capacity.
Downgrade takes effect next period. Over-limit preserves data and allows reduction and
sale of existing stock, blocking increases; team deactivation is owner controlled.

PROPOSED active donor: added or being dismantled, including fully dismantled donor with
remaining stock/reservations. Archive is non-destructive. Active residual stock/reserves
prevent releasing a garage place. Toggling a part archive flag, hiding assortment or
removing provenance must not evade quota. Returns preserve physical inventory, even
if they create over-limit. All ingress paths need an atomic workspace quota guard.

PROPOSED team: owner + 5/10 active staff; inactive staff excluded. Future unexpired
invitations reserve seats. Reactivation must use the same quota transaction as create.
Role ADMIN does not imply financial permissions.

PROPOSED trial: one 10-day trial per customer/company, Standard or Premium; no required
card and no automatic paid conversion. Switching trial plan cannot reset its deadline.
PROPOSED grace: 72 hours after paid expiry, never extended by repeated retries. Free/
Expired retain view/search/history/export/payment and safe completion of existing
obligations, cancellation/release and genuine returns. New stock/donors/orders and
paid mutations are restricted only in a later package, with backend entitlements.

PROPOSED billing calendar: UTC half-open paid intervals, Kyiv display; monthly anchor
restored after shorter months. Early renewal extends from paid-through, not now.
Advance multi-month payment must suppress redundant recurring collections. This phase
accepts explicit periods; it does not implement a recurring calendar scheduler.

PROPOSED referral: once per new paid customer across ecosystem, 20% base, 25-30% approved
partner/campaign policy. Base is externally funded portion of first monthly base tariff
after discount, excluding add-ons and bonus funding. Topup alone is not qualification.
Funding provenance required for wallet payments. Hold 30 days; minimum payout 500 UAH.
Refund/chargeback reverses corresponding reward. No monthly renewal reward, self-referral,
cycles or bonus-funded reward loops. No referral engine is implemented in Phase 1.

Main funds, withdrawable earned referral funds and nonwithdrawable promotional funds
are separate balances. No employee/company merging. No user-to-user money transfer.
Wallet legal/accounting status, tax handling, referral deductions and payout eligibility
remain BLOCKED pending accountant/lawyer/provider confirmation. No payout implementation.

Open decisions: final add-on cadence, financial calendar, trial abuse checks, safe-operation
matrix, grace rights, referral net/gross tax base, hold/minimum, bonus spend priority,
company ownership transfer, merchant capabilities and production financial DB placement.
