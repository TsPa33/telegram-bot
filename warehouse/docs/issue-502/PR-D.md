# Draft PR preparation — #502 D: Shared corporate workspace UX

Status: **prepared locally, not published** (owner instruction). Stack onto `fix/warehouse-502-c-checkout`, base `af2f01b8badd01fa7b5a6cb8f8170cd67e737bb5`; head branch `fix/warehouse-502-d-shared-ux`. Do not target main. Preserve PR499/501.

Reuse category/list/inspector in sales, compact PartCard actions, keyboard/desktop/mobile navigation, Settings General/Payments status only and admin diagnostics. No provider integration.

Validation: Frontend258/build; real local day/night1440/1920/390, keyboard/mobile focus/theme persistence/no overflow; final functional browser evidence. These are isolated local test records, never live staging evidence. See [acceptance](ACCEPTANCE.md), [audit](AUDIT.md) and evidence logs/screenshots. No production/staging mutations, paid calls, new migrations/backfills or history rewrite.

DONE locally: reviewed focused diff; tests/build and browser evidence; guarded stock transitions and unchanged working data. DONE for staging remains conditional on the separately authorized operator steps in ACCEPTANCE.md. Qty6 extraction remains blocked, no automatic cost allocation. Actual Peugeot34/year and live VIN source/staging are unverified.

Rollback: application change only; preserve recorded ledger/history and existing VIN evidence, no downgrade/delete/reset. Publish as Draft and review in stack order; no automatic merge or deploy.
