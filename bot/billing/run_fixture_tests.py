"""Run only billing tests on two fresh local PostgreSQL databases; always remove container.

Usage: python -m bot.billing.run_fixture_tests (from repository root, test deps installed).
Never reads a user-supplied DB URL. Requires the managed local Docker socket.
"""

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
import psycopg2


def main():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGOPTIONS",
        "PGHOSTADDR",
    ):
        env.pop(key, None)
    docker = ["docker", "--host=unix:///var/run/docker.sock"]
    name = "carpot-billing-test-" + uuid4().hex[:12]
    password = secrets.token_hex(24)
    # Image digest used during acceptance, PostgreSQL 16 Alpine.
    image = "postgres:16-alpine@sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139"
    # Rootless Docker's allocator may choose a port occupied by another host process.
    # Ask the host OS for a free loopback port instead of relying on its port range.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        requested_port = listener.getsockname()[1]

    def command(args, **kwargs):
        return subprocess.check_output(
            docker + args, env=env, text=True, **kwargs
        ).strip()

    try:
        command(
            [
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--publish",
                f"127.0.0.1:{requested_port}:5432",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "--env",
                "POSTGRES_DB=carpot_billing_foundation_test",
                "--tmpfs",
                "/var/lib/postgresql/data",
                image,
            ]
        )
        info = json.loads(command(["inspect", name]))[0]
        port = info["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
        ready = False
        for _ in range(60):
            check = subprocess.run(
                docker
                + ["exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if check.returncode == 0:
                ready = True
                break
            time.sleep(0.25)
        if not ready:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        command(
            [
                "exec",
                name,
                "createdb",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "carpot_billing_projection_test",
            ]
        )
        for variable, database in [
            ("CARPOT_BILLING_TEST_DSN", "carpot_billing_foundation_test"),
            ("CARPOT_BILLING_PROJECTION_TEST_DSN", "carpot_billing_projection_test"),
        ]:
            env[variable] = psycopg2.extensions.make_dsn(
                host="127.0.0.1",
                port=port,
                dbname=database,
                user="postgres",
                password=password,
            )
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                "bot/billing/pytest.ini",
                "bot/billing/tests",
                "-q",
                "--tb=short",
            ],
            cwd=root,
            env=env,
        )
    finally:
        subprocess.run(
            docker + ["rm", "--force", name],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
