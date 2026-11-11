# Draft PR preparation — #502 C: One atomic order checkout

Status: **prepared locally, not published** (owner instruction). Stack onto `fix/warehouse-502-b-assembly`, base `bcad7e65435e22b6899be70ae651f6393916c77f`; head branch `fix/warehouse-502-c-checkout`. Do not target main. Preserve PR499/501.

Replace primary direct-sale UI with one order basket, optional search, explicit draft/reserve/sale; reuse order transaction/request ledger and assembly confirmations. Align index metadata to existing index; preserve forward-only migration guard.

Validation: Order/assembly81, checkout11 (5 overlap), team23, Alembic check; real local 1/2-line price/currency/sale/reload browser. These are isolated local test records, never live staging evidence. See [acceptance](ACCEPTANCE.md), [audit](AUDIT.md) and evidence logs/screenshots. No production/staging mutations, paid calls, new migrations/backfills or history rewrite.

DONE locally: reviewed focused diff; tests/build and browser evidence; guarded stock transitions and unchanged working data. DONE for staging remains conditional on the separately authorized operator steps in ACCEPTANCE.md. Qty6 extraction remains blocked, no automatic cost allocation. Actual Peugeot34/year and live VIN source/staging are unverified.

Rollback: application change only; preserve recorded ledger/history and existing VIN evidence, no downgrade/delete/reset. Publish as Draft and review in stack order; no automatic merge or deploy.
