"""Explicit operator commands. No migration, provisioning or source sync at startup."""

import argparse
import getpass
from pathlib import Path
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .config import cipher, connection, environment
from .models import Staff
from .security import audit, hasher, mfa_step, revoke


def migrate():
    # Explicit operator process only, never runtime startup.
    engine = connection("CONTROL_CENTER_MIGRATOR_URL")
    directory = Path(__file__).resolve().parents[2] / "control_center_migrations"
    with engine.begin() as c:
        c.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('control-center-migrate'))")
        )
        exists = c.scalar(text("SELECT to_regclass('control_center.schema_version')"))
        if exists:
            version, source_env = c.execute(
                text("SELECT version,environment FROM control_center.schema_version")
            ).one()
            if version not in {"001", "002"} or source_env != environment():
                raise RuntimeError("Control Center schema/environment mismatch")
        else:
            c.connection.driver_connection.execute((directory / "001.sql").read_text())
            c.execute(
                text("INSERT INTO control_center.schema_version VALUES ('001',:e)"),
                {"e": environment()},
            )
            version = "001"
        if version == "001":
            c.connection.driver_connection.execute((directory / "002.sql").read_text())


def provision(db, username, role, password, secret, code):
    if (
        len(password) < 12
        or len(password) > 128
        or not username.strip()
        or role not in {"Owner", "Administrator", "Manager", "Support", "Moderator"}
    ):
        raise ValueError("Invalid staff provisioning fields")
    step = mfa_step(secret, code)
    if step is None:
        raise ValueError("MFA enrollment confirmation required")
    row = Staff(
        username=username.strip().lower(),
        role=role,
        password_hash=hasher.hash(password),
        mfa_ciphertext=cipher().encrypt(secret.encode()).decode(),
        last_totp_step=step,
        active=True,
        finance=False,
    )
    db.add(row)
    db.flush()
    audit(db, "operator", "staff.provision", "staff", row.id, diff={"role": role})
    db.commit()
    return row.id


def reset_password(db, username, password):
    if not 12 <= len(password) <= 128:
        raise ValueError("Password length must be 12–128")
    row = db.scalar(
        select(Staff)
        .where(Staff.username == username.strip().lower())
        .with_for_update()
    )
    if not row:
        raise ValueError("Staff not found")
    row.password_hash = hasher.hash(password)
    revoke(db, row.id)
    audit(db, "operator", "staff.password_reset", "staff", row.id)
    db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["migrate", "provision", "reset-password", "sync"]
    )
    parser.add_argument("--username")
    parser.add_argument(
        "--role",
        choices=["Owner", "Administrator", "Manager", "Support", "Moderator"],
        default="Owner",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
        return
    if args.command in {"provision", "reset-password"}:
        # Operator DB role, not a credential available to the web process.
        engine = connection("CONTROL_CENTER_OPERATOR_URL")
        if not args.username:
            parser.error("--username required")
        password = getpass.getpass("New staff password (12–128 characters): ")
        if len(password) < 12 or len(password) > 128:
            raise ValueError("Password length must be 12–128")
        with Session(engine) as db:
            if args.command == "provision":
                # Enter a securely shared authenticator seed; no seed is logged/output.
                secret = (
                    getpass.getpass("Base32 MFA seed from secure enrollment channel: ")
                    .strip()
                    .upper()
                )
                code = getpass.getpass("Current authenticator code: ").strip()
                provision(db, args.username, args.role, password, secret, code)
            else:
                reset_password(db, args.username, password)
        return
    from .projection import sync_batch

    with Session(connection(), expire_on_commit=False) as db:
        result = sync_batch(db, args.limit)
        print(result)


if __name__ == "__main__":
    try:
        main()
    except (SQLAlchemyError, RuntimeError, KeyError, ValueError):
        raise SystemExit(
            "Control Center command failed. Check approved configuration, input and operator permissions; no credentials are logged."
        ) from None
