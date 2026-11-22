# CarPot Oracle OEM — Tailscale Railway Egress (Stage 4, 2026-11-22)

## Confirmed Oracle runtime

- Tailscale node: `carpot-oracle`, private IP `100.87.244.120`.
- Tailscale Serve (tailnet-only): `https://carpot-oracle.tailf95906.ts.net/` -> `http://127.0.0.1:8081`.
- Oracle Adapter: systemd `enabled` and `active`; restricted MySQL user `carpot_catalogue_ro` has SELECT on three source tables.
- Confirmed live query: supplier 1, article 20064, maker 120 -> OEM 272440, 31256231, 31256232.
- No public Oracle Adapter/MySQL port; source import may continue.

## Why a Railway Tailscale node is still required

The HTTPS `*.ts.net` URL is reachable only from a Tailscale device with matching permissions. Railway does not become a tailnet member just by storing the URL. Use a **separate, internal-only Railway service** running the **official Tailscale image**. The service's HTTP CONNECT proxy gives Catalogue API an explicit route to the Tailscale node while maintaining HTTPS and validating the Oracle certificate.

## Tailscale relay service (not yet provisioned)

Deploy in project `selfless-caring`, environment `catalogue-staging` only, never production.

- Service name and Railway private DNS: `carpot-oracle-relay` -> `carpot-oracle-relay.railway.internal`.
- Docker image: `tailscale/tailscale:stable` (official).
- Networking: **private-only**; do not generate a Railway public domain or TCP public proxy.
- Variables:
  - `TS_AUTHKEY`: Tailscale auth key, created in Tailscale admin console and entered directly into Railway secret variable. Never paste in chat or GitHub.
  - `TS_USERSPACE=true`
  - `TS_OUTBOUND_HTTP_PROXY_LISTEN=:1055`
  - `TS_HOSTNAME=carpot-catalogue-relay`
  - `TS_ACCEPT_DNS=false`
  - `TS_EXTRA_ARGS=--accept-routes=false --ssh=false`
  - `TS_KUBE_SECRET=` (optional, use Tailscale's default if not set; confirm when deploying)

For disposable Railway containers choose a reusable, ephemeral Tailscale auth key, with limited expiry and a restrictive node policy; rotate/revoke on compromise. If device approval is enabled, approve only the intended relay. Restrict the relay's tailnet egress to Oracle port 443 with Tailscale ACL/grants. Do not route MySQL port 3306.

## Catalogue API gateway on GitHub

`catalogue/oracle_gateway.py` supports an OPTIONAL named HTTP CONNECT proxy:

- `ORACLE_ADAPTER_URL=https://carpot-oracle.tailf95906.ts.net`
- `ORACLE_HTTP_PROXY=http://carpot-oracle-relay.railway.internal:1055`
- `ORACLE_ADAPTER_KEY`: API key created earlier on Oracle, entered as secret into Catalogue staging only by approved secure mechanism; **do not print, copy to chat or commit**.
- `ORACLE_CATALOGUE_ENABLED=true` only AFTER relay proves reachable and the gateway is deployed to `catalogue-staging`.

Unrecognized proxy URL is refused. Requests remain HTTPS end-to-end from Catalogue client to Oracle Serve using HTTP CONNECT through Railway-private Tailscale relay. The Railway-only connection to the proxy stays within Railway private network. Existing Catalogue routes are unchanged, and the Oracle feature defaults to off. No Warehouse automatic assignment until exact vehicle fitment source has been checked.

## Next checkpoints (release gates)

1. User creates a scoped Tailscale key **in the console**, stores it directly in Railway service.
2. Deploy official Tailscale relay to Railway `catalogue-staging` only; verify internal-only networking and Tailscale node online. No public domain.
3. Confirm relay can connect to `carpot-oracle.tailf95906.ts.net:443` (CONNECT, normal TLS cert validation), and the existing Oracle API key remains secret.
4. Deploy Catalogue staging branch through a reviewed, isolated rollout; check feature flag disabled preserves current services.
5. Configure `ORACLE_ADAPTER_URL`, `ORACLE_HTTP_PROXY`, `ORACLE_ADAPTER_KEY`, and finally enable `ORACLE_CATALOGUE_ENABLED`.
6. Verify OEM lookup 20064 and 272440 through `catalogue-staging`; verify failures return 503 and do not affect ordinary catalogue operations.
7. Preserve production and warehouse source writes. Only after full `article_links` import and validated vehicle/article data can the Warehouse auto-OEM fitment work proceed.

## Actual state

- Added support in the code branch and two offline proxy-configuration assertions.
- **Not yet deployed** in Railway; no Tailscale key available in the assistant session.
- Proxy reachability and end-to-end Railway request **not yet tested**.
- Import status after the last source update is not verified.

References:
- Tailscale Docker configuration: https://tailscale.com/docs/features/containers/docker/docker-params
- Tailscale userspace networking: https://tailscale.com/docs/concepts/userspace-networking
- Railway private networking: https://docs.railway.com/networking/private-networking
