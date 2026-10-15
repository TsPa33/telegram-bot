"""LOCAL integration checks only. Never connects to Railway or CarPot.

Build the two staging images first. Creates and destroys a dedicated Compose
project with a warehouse_staging_test database; PostgreSQL has no host port.
"""

import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
env = dict(os.environ, WAREHOUSE_STAGING_CHECK_PASSWORD=secrets.token_hex(32))
env.setdefault(
    "DOCKER_CONFIG", str(Path(tempfile.gettempdir()) / "warehouse-docker-config")
)
env.setdefault("BUILDX_CONFIG", str(Path(tempfile.gettempdir()) / "warehouse-buildx"))
compose = ["docker", "compose", "-f", str(ROOT / "compose.check.yml")]
fixture = ROOT / ".check"
fixture.mkdir(mode=0o700, exist_ok=True)
fixture.chmod(0o700)


def run(args, **kwargs):
    return subprocess.run(args, env=env, check=True, **kwargs)


def dc(*args, **kwargs):
    return run([*compose, *args], **kwargs)


def execute_sql(sql):
    return dc(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "warehouse_check",
        "-d",
        "warehouse_staging_test",
        "-Atc",
        sql,
        capture_output=True,
        text=True,
    ).stdout.strip()


try:
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(fixture / "key.pem"),
            "-out",
            str(fixture / "cert.pem"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (fixture / "key.pem").chmod(0o600)
    dc("config", "--quiet")
    dc(
        "--profile",
        "test",
        "up",
        "--no-build",
        "--abort-on-container-exit",
        "--exit-code-from",
        "tests",
        "tests",
    )
    assert execute_sql("SELECT current_database()") == "warehouse_staging_test"
    execute_sql(
        "TRUNCATE photos, operations, parts, categories, vehicles, sessions, accounts CASCADE"
    )
    dc("up", "--no-build", "-d", "edge")
    origin = "https://localhost:18443"
    context = ssl.create_default_context(cafile=str(fixture / "cert.pem"))
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(cookies),
        urllib.request.ProxyHandler({}),
    )
    csrf = ""

    def request(path, method="GET", body=None, *, request_origin=origin, token=None):
        headers = {}
        if method != "GET":
            headers = {
                "Content-Type": "application/json",
                "Origin": request_origin,
                "X-CSRF-Token": csrf if token is None else token,
            }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            origin + path, data=data, method=method, headers=headers
        )
        try:
            r = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            r = error
        raw = r.read()
        result = (
            json.loads(raw)
            if raw and "application/json" in r.headers.get("Content-Type", "")
            else raw.decode()
        )
        return r.status, result, r.headers

    def ready():
        for _ in range(60):
            try:
                if request("/health")[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError("Local staging HTTPS health never became ready")

    ready()
    assert execute_sql("SELECT count(*) FROM accounts") == "0"
    assert execute_sql("SELECT count(*) FROM parts") == "0"
    assert request("/api/v1/auth/options")[1] == {"registration_enabled": False}
    assert (
        request(
            "/api/v1/auth/register",
            "POST",
            {
                "name": "Closed registration check",
                "email": "closed@example.test",
                "password": secrets.token_urlsafe(24),
            },
        )[0]
        == 403
    )
    assert request("/api/v1/dashboard")[0] == 401
    status, html, headers = request("/inventory")
    assert status == 200 and "root" in html and "/@vite/client" not in html
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    assert "noindex" in headers["X-Robots-Tag"]
    asset = re.search(r'src="(/assets/[^\"]+\.js)"', html).group(1)
    assert request(asset)[0] == 200
    assert request("/assets/not-a-real-file.js")[0] == 404
    status, data, _ = request("/api/v1/not-a-real-route")
    assert status == 404 and isinstance(data, dict)

    # Test fixture creation is allowed ONLY in this throwaway *_test database.
    password = secrets.token_urlsafe(32)
    account = {"email": "warehouse-staging-check@example.test", "password": password}
    seed = """import json,sys
from sqlalchemy.orm import Session
from app.db import engine
from app.config import database_url
from sqlalchemy.engine import make_url
from app.models import Account
from app.services.auth import hasher
assert make_url(database_url()).database == 'warehouse_staging_test'
data=json.load(sys.stdin)
with Session(engine()) as db:
 db.add(Account(name='Local staging test fixture',email=data['email'],password_hash=hasher.hash(data['password'])))
 db.commit()
"""
    dc("exec", "-T", "api", "python", "-c", seed, input=json.dumps(account), text=True)
    status, login, headers = request("/api/v1/auth/login", "POST", account)
    assert status == 200
    set_cookies = headers.get_all("Set-Cookie")
    assert all("Secure" in c and "SameSite=strict" in c for c in set_cookies)
    assert "HttpOnly" in set_cookies[0] and "Path=/api/v1" in set_cookies[0]
    csrf = login["csrf_token"]
    assert request("/api/v1/auth/me")[0] == 200
    vehicle = {
        "manufacturer": "Local test fixture",
        "model": "Transport check",
        "year": 2020,
        "donor_id": "LOCAL-CHECK",
        "acquisition_date": "2026-01-01",
    }
    assert request("/api/v1/vehicles", "POST", vehicle, token="incorrect")[0] == 403
    assert (
        request(
            "/api/v1/vehicles",
            "POST",
            vehicle,
            request_origin="https://other.example.test",
        )[0]
        == 403
    )
    assert request("/api/v1/vehicles", "POST", vehicle)[0] == 201
    # The root bootstrap must have dropped privileges BEFORE migrations/serving.
    uid = dc(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "print(next(l for l in open('/proc/1/status') if l.startswith('Uid:')).split()[1])",
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert uid == "1000"
    print(
        "PASS: real HTTPS, production assets/SPA, API status preservation, secure session cookies, CSRF/origin checks, no seeds, non-root API",
        flush=True,
    )

    credential_file = fixture / "browser.json"
    credential_file.write_text(json.dumps({**account, "origin": origin}))
    credential_file.chmod(0o600)
    run(["node", str(ROOT / "check-browser.mjs")], cwd=ROOT.parents[1] / "frontend")
    credential_file.unlink()

    dc("stop", "api")
    assert request("/health")[0] != 200
    dc("up", "--no-build", "-d", "--no-deps", "--force-recreate", "api")
    ready()
    assert request("/api/v1/auth/me")[0] == 200
    assert execute_sql("SELECT count(*) FROM vehicles") == "1"
    assert request("/api/v1/auth/logout", "POST")[0] == 204
    assert request("/api/v1/auth/me")[0] == 401
    print(
        "PASS: unhealthy backend fails frontend readiness; startup/migrations repeat; DB/session persist across API replacement; logout revokes session",
        flush=True,
    )
finally:
    subprocess.run(
        [*compose, "--profile", "test", "down", "-v", "--remove-orphans"],
        env=env,
        check=False,
    )
    for name in ("key.pem", "cert.pem", "browser.json"):
        (fixture / name).unlink(missing_ok=True)
