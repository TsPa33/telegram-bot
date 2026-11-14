# Next implementation packages

## Warehouse capacity / team / trial / Free / Expired

Prerequisites: owner-approved business policy, verified company binding, authenticated
internal transport, chosen operational financial DB. Do not bind to observed offline
production merely because the repository already has a DATABASE_URL setting.

1. Introduce centralized product entitlement policy intersected with Warehouse RBAC.
2. Replace dismantling-credit semantics with persistent capacity grants. Inventory review
   before any legacy conversion; preserve credits/history until explicit decision.
3. Add workspace row-lock capacity checks to routes.vehicle_create,
   unified_catalogue.global_vehicle, vehicle restore and all future donor import paths.
   Vehicle directory import is a reference catalogue, not donor creation.
4. Archive checks use donor-linked physical stock, reserves, orders, returns and provenance;
   prevent hiding stock via archived parts/detached donor IDs.
5. Team creation/reactivation/invitation acceptance share one atomic seat guard.
6. One 10-day company trial claim, no card; no deadline reset by plan switch.
7. Replace blanket mutation paywall in api/deps.py with safe-operation policy: view/export,
   release/cancel/returns and pre-existing order completion remain possible on expiry.
8. Add tests for parallel creation/import/restore, returns after archive, expiry while
   orders reserved, over-limit downgrade and staff financial isolation.

Acceptance: 10/50 continuous garage capacity, owner+5/10 staff, no data loss, no frontend/API
bypass, expired access matrix enforced centrally. Rollback disables new routing while
retaining payment, entitlement and inventory evidence. No automatic deletion/deactivation.

## LiqPay manual Checkout

Resolve provider-contract.md blockers first. Implement raw verified callback adapter,
intent status query, one-time Checkout and reconciliation. Validate merchant, amount,
currency, environment and IDs. Never activate from result_url or sandbox events. Preserve
legacy callback routing and seller subscriptions. Contract tests precede authorized sandbox
acceptance; production activation is a separate approval. Refund and recurring have their
own lifecycle/consent requirements. Do not wallet-fallback while provider retries can charge.

## Parallel ownership

Contracts/UI design may proceed independently from implementation after version approval.
One owner for shared finance schema/provider state machine; serialize migrations. Warehouse
quota module and frontend can use frozen contract mocks, with distinct file ownership.
No automatic deployment, Railway mutations, real payments or worker changes in these plans.
