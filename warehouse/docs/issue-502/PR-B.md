# Draft PR preparation — #502 B: Interactive assembly references

Status: **prepared locally, not published** (owner instruction). Stack onto `fix/warehouse-502-a-vin-plan`, base `7c856cbcb28318195eb2ed53f3d9140b96b85705`; head branch `fix/warehouse-502-b-assembly`. Do not target main. Preserve PR499/501.

Select reference components into existing physical split inspector; no automatic SKU/presence. Preserve qty1 transaction and explicit qty6 blocker.

Validation: 55 physical backend tests, real local auth/PG browser qty1/qty6, preview failure, references and confirmed split; 1440/390. These are isolated local test records, never live staging evidence. See [acceptance](ACCEPTANCE.md), [audit](AUDIT.md) and evidence logs/screenshots. No production/staging mutations, paid calls, new migrations/backfills or history rewrite.

DONE locally: reviewed focused diff; tests/build and browser evidence; guarded stock transitions and unchanged working data. DONE for staging remains conditional on the separately authorized operator steps in ACCEPTANCE.md. Qty6 extraction remains blocked, no automatic cost allocation. Actual Peugeot34/year and live VIN source/staging are unverified.

Rollback: application change only; preserve recorded ledger/history and existing VIN evidence, no downgrade/delete/reset. Publish as Draft and review in stack order; no automatic merge or deploy.
