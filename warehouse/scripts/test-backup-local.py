"""Disposable local PostgreSQL dump/restore test. Never connects to Railway."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=str(ROOT / ".venv/bin/python"), help="Python with Warehouse dependencies")
    parser.add_argument("--docker-config", help="Optional Docker CLI configuration directory")
    args = parser.parse_args()
    docker = ["docker"] + (["--config", args.docker_config] if args.docker_config else [])
    prefix = "warehouse-backup-local-" + secrets.token_hex(4)
    source, target = prefix + "-source", prefix + "-restore"
    password = secrets.token_urlsafe(32)  # Disposable local container ONLY.
    env = dict(os.environ, POSTGRES_PASSWORD=password, WAREHOUSE_DB_PASSWORD=password)
    resources = []
    stage = "source startup"

    def run(command, **kwargs):
        return subprocess.run(command, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=kwargs.pop("env", env), **kwargs)

    def ready(name):
        for _ in range(30):
            # Initdb briefly exposes a Unix socket BEFORE creating POSTGRES_DB.
            # Require the real TCP server AND the intended database, not that socket.
            probe = 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X --no-password -h 127.0.0.1 -U "${POSTGRES_USER:-postgres}" -d "$POSTGRES_DB" -At -c "SELECT 1"'
            if subprocess.run(docker + ["exec", name, "sh", "-c", probe], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("Local PostgreSQL did not start")

    def sql(name, query, owner="postgres", database="warehouse_restore_test"):
        return run(docker + ["exec", name, "psql", "-X", "--no-password", "-qAt", "-U", owner,
                            "-d", database, "-c", query]).stdout.decode()

    def snapshot(name, owner, database):
        tables = sql(name, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename", owner, database).splitlines()
        result = {"tables": tables}
        for table in tables:
            if not re.fullmatch(r"[a-z_]+", table):
                raise RuntimeError("Unexpected local test table")
            result[table] = sql(name, f"SELECT row_to_json(t)::text FROM (SELECT * FROM public.{table} ORDER BY 1) t", owner, database)
        return result

    try:
        resources.append(source)
        run(docker + ["run", "--rm", "-d", "--name", source, "-p", "127.0.0.1::5432",
                      "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_USER=warehouse_test_owner",
                      "-e", "POSTGRES_DB=warehouse_backup_test", "postgres:16-alpine"])
        ready(source)
        port = run(docker + ["port", source, "5432"]).stdout.decode().strip().rsplit(":",1)[1]
        app_env = dict(env, WAREHOUSE_DATABASE_URL=f"postgresql+psycopg://warehouse_test_owner:{password}@127.0.0.1:{port}/warehouse_backup_test", PYTHONPATH=".")
        stage = "local SQL fixture setup (no Alembic migrations)"
        seed = '''from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import Base, engine
from app.models import Account, Vehicle, Part, Operation
Base.metadata.create_all(engine())
with engine().begin() as conn:
    conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
    conn.execute(text("INSERT INTO alembic_version VALUES ('offline_fixture')"))
    conn.execute(text("CREATE FUNCTION warehouse_reject_audit_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Warehouse audit history is immutable'; END; $$"))
    conn.execute(text("CREATE TRIGGER immutable_warehouse_audit BEFORE UPDATE OR DELETE ON operations FOR EACH ROW EXECUTE FUNCTION warehouse_reject_audit_change()"))
with Session(engine()) as db:
    account=Account(email="backup@example.test",name="Offline backup test",password_hash="not-a-login")
    db.add(account);db.flush()
    vehicle=Vehicle(account_id=account.id,manufacturer="Synthetic",model="Backup fixture",year=2020,donor_id="BACKUP-LOCAL",acquisition_date=date(2020,1,1),ktype=None)
    db.add(vehicle);db.flush()
    part=Part(account_id=account.id,vehicle_id=vehicle.id,name="Synthetic fixture",quantity=2,reserved_quantity=1,availability="present")
    db.add(part);db.flush()
    db.add(Operation(account_id=account.id,actor_id=account.id,part_id=part.id,vehicle_id=vehicle.id,entity_id=part.id,entity_type="parts",type="receipt",reason="Offline backup fixture",before={},after={"quantity":2}))
    db.commit()
'''
        run([args.python,"-c",seed],cwd=ROOT / "backend",env=app_env)
        for revision in ("offline_fixture",):
            stage = "source snapshot " + revision
            before = snapshot(source, "warehouse_test_owner", "warehouse_backup_test")
            stage = "dump " + revision
            result = run(docker + ["exec", "-i", "-e", "WAREHOUSE_DB_HOST=127.0.0.1",
                         "-e", "WAREHOUSE_DB_PORT=5432", "-e", "WAREHOUSE_DB_NAME=warehouse_backup_test",
                         "-e", "WAREHOUSE_DB_USER=warehouse_test_owner", "-e", "WAREHOUSE_DB_PASSWORD",
                         source, "sh", "-s", "--", "--local-test"], input=(ROOT / "scripts/backup-staging.sh").read_bytes())
            directory = re.search(rb"Temporary directory: (/tmp/warehouse-backup\.[A-Za-z0-9]+)", result.stdout)
            if not directory:
                raise RuntimeError("Backup command did not return a temporary directory")
            directory = directory[1].decode()
            assert snapshot(source,"warehouse_test_owner","warehouse_backup_test") == before
            with tempfile.TemporaryDirectory(prefix="warehouse-backup-verify-") as local:
                # Replay the EXACT sender+receiver through local non-TTY pipes.
                # Only the transport is substituted: Docker exec, not Railway SSH.
                transfer_spec=importlib.util.spec_from_file_location("backup_transfer",ROOT / "scripts/backup-railway.py")
                transfer=importlib.util.module_from_spec(transfer_spec);transfer_spec.loader.exec_module(transfer)
                _, sender = transfer.command("local-project","postgres",transfer=True,fetch_directory=directory)
                invocation=docker + ["exec","-i","-e","RAILWAY_PROJECT_ID=local-project",
                                    "-e","RAILWAY_ENVIRONMENT_NAME=warehouse-staging",
                                    "-e","RAILWAY_SERVICE_NAME=postgres",source,"sh","-s","--","--confirm-warehouse-staging"]
                downloaded, remote = transfer.download(invocation,sender,Path(local)/"received")
                assert remote == directory
                archive = downloaded / "warehouse-staging.dump"
                assert (downloaded / "source-revision.txt").read_text().strip() == revision
                spec=importlib.util.spec_from_file_location("backup_verifier",ROOT / "scripts/verify-backup.py")
                verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
                stage = "archive verification " + revision
                verifier.verify(archive,docker=True,docker_config=args.docker_config)
                resources.append(target)
                run(docker + ["run", "--rm", "-d", "--name", target, "--network", "none",
                              "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=warehouse_restore_test", "postgres:16-alpine"])
                stage = "restore startup " + revision
                ready(target)
                with archive.open("rb") as stream:
                    run(docker + ["exec", "-i", target, "pg_restore", "--exit-on-error", "--single-transaction",
                                  "--no-owner", "--no-acl", "-U", "postgres", "-d", "warehouse_restore_test"], stdin=stream)
                stage = "restored rows " + revision
                assert snapshot(target,"postgres","warehouse_restore_test") == before
                rejected=subprocess.run(docker + ["exec",target,"psql","-X","-U","postgres","-d","warehouse_restore_test","-v","ON_ERROR_STOP=1","-c","UPDATE operations SET reason='must fail'"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                assert rejected.returncode != 0
                stage = "checksum corruption rejection " + revision
                archive.write_bytes(archive.read_bytes()+b"X")
                try:
                    verifier.verify(archive)
                except ValueError:
                    pass
                else:
                    raise RuntimeError("Corrupted dump was accepted")
                # A matching checksum alone cannot validate a damaged archive.
                stage = "archive corruption rejection " + revision
                archive.write_bytes(archive.read_bytes()[:10])
                archive.with_name(archive.name+".sha256").write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n")
                try:
                    verifier.verify(archive,docker=True,docker_config=args.docker_config)
                except ValueError:
                    pass
                else:
                    raise RuntimeError("Truncated archive with recomputed checksum was accepted")
                run(docker + ["rm","-f","-v",target]);resources.remove(target)
            run(docker + ["exec",source,"rm","-rf",directory])
            print("PASS: dump, SHA-256, full decode, separate PostgreSQL restore, all rows, immutable audit, revision",revision)
        return 0
    except (OSError, RuntimeError, AssertionError, ValueError, subprocess.SubprocessError) as exc:
        print("Local backup test failed at",stage,"("+type(exc).__name__+"); raw diagnostics suppressed.",file=sys.stderr)
        return 1
    finally:
        for name in reversed(resources):
            subprocess.run(docker + ["rm","-f","-v",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
