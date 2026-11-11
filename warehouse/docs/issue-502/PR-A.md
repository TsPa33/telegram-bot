# Draft PR preparation — #502 A: VIN and visible free base plan

Status: **prepared locally, not published** (owner instruction). Stack onto `fix/warehouse-500-split-visibility`, base `a0d00c2e39135bee88e5c4e1bdf3adea5649b8ce`; head branch `fix/warehouse-502-a-vin-plan`. Do not target main. Preserve PR499/501.

Free plan was hidden in collapsed controls; expose it for every make without tokens. Flag ambiguous year and persist bounded evidence in existing vin_details.

Validation: 29 backend tests, 3-brand real local browser save/reopen/no stock, fixture-only VIN form edit/persistence. These are isolated local test records, never live staging evidence. See [acceptance](ACCEPTANCE.md), [audit](AUDIT.md) and evidence logs/screenshots. No production/staging mutations, paid calls, new migrations/backfills or history rewrite.

DONE locally: reviewed focused diff; tests/build and browser evidence; guarded stock transitions and unchanged working data. DONE for staging remains conditional on the separately authorized operator steps in ACCEPTANCE.md. Qty6 extraction remains blocked, no automatic cost allocation. Actual Peugeot34/year and live VIN source/staging are unverified.

Rollback: application change only; preserve recorded ledger/history and existing VIN evidence, no downgrade/delete/reset. Publish as Draft and review in stack order; no automatic merge or deploy.
