"""Read-only local checks; never calls Railway or reads deployment secrets."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
config = json.loads((ROOT / "services.json").read_text())
services = config["services"]
assert set(services) == {"warehouse-web", "warehouse-api", "warehouse-db"}
for name in ("warehouse-web", "warehouse-api"):
    service = services[name]
    assert service["source"]["rootDirectory"] == "/warehouse"
    assert service["source"]["branch"] == "feature/carpot-warehouse-mvp"
    assert service["source"]["repository"] == "TsPa33/telegram-bot"
    assert service["healthcheckPath"] == "/health" and service["replicas"] == 1
    assert (ROOT.parents[1] / service["dockerfilePath"]).is_file()
    assert all(path.startswith("/warehouse/") for path in service["watchPaths"])
assert services["warehouse-web"]["publicDomain"] is True
for name in ("warehouse-api", "warehouse-db"):
    assert services[name]["publicDomain"] is False
assert services["warehouse-db"]["tcpProxy"] is False
assert services["warehouse-db"]["variables"]["POSTGRES_DB"] == "warehouse_staging"
assert services["warehouse-db"]["volume"]["mountPath"] == "/var/lib/postgresql/data"
api = services["warehouse-api"]["variables"]
assert api["WAREHOUSE_COOKIE_SECURE"] == "true"
assert api["WAREHOUSE_REGISTRATION_ENABLED"] == "false"
assert "*" not in api["WAREHOUSE_FORWARDED_ALLOW_IPS"]
assert api["WAREHOUSE_DB_PASSWORD"] == "${{warehouse-db.POSTGRES_PASSWORD}}"
assert "WAREHOUSE_DB_PASSWORD" not in services["warehouse-web"]["variables"]
subprocess.run(["sh", "-n", str(ROOT / "frontend-start.sh")], check=True)
print(
    "PASS: isolated service settings, private DB/API, HTTPS cookies, source/watch paths and shell syntax"
)
print(
    "This validates local configuration invariants, not Railway API acceptance or a deployment."
)
