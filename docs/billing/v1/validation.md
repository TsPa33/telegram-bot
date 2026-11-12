# Phase 1 validation

Local PostgreSQL 16 on the managed local Docker daemon; tmpfs data, loopback port,
separate finance and projection DBs. No Railway variables, live DB connection,
LiqPay keys, payment, real webhook, refund, payout or deployment used.

Tests cover exact money and HALF_UP proration; DST normalization; disposable DSN and
ambient libpq refusal; disabled defaults; migration reapplication and non-destructive
rollback; invoice issue/void/idempotency; immutable catalogue/invoice/journal evidence;
deferred journal balance; concurrent invoice/settlement/event handling; provider mismatch;
duplicate/colliding/late events; duplicate external transaction; tenant composite FKs;
server membership permissions; personal/company separation; settlement crash rollback;
payment commit before projection; consumer commit before finance ack; outbox replay;
monotonic full snapshots, future/late periods and consumer binding checks.

Legacy regression evidence is bounded: original CarPot runtime and Warehouse files are
byte-for-byte unchanged from the approved SHA; an isolated AST-based test executes the
original Checkout class with a DB stub and synthetic keys, confirming its existing
payload/signature behavior without importing runtime startup or contacting providers.
This preserves existing sandbox behavior, not endorsement of its production safety.
Full legacy/Warehouse integration suites and real provider compatibility are not claimed.

Automated CI workflow is supplied; local results are distinct from remote CI status.
Final local acceptance result and published SHA are recorded in the Draft PR description.
