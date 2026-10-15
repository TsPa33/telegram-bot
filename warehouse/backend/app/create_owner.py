"""Interactively create a REAL staging owner; never seed or pass passwords in argv."""

import getpass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import is_staging
from app.db import engine
from app.models import Account
from app.schemas import Registration
from app.services.auth import hasher


def main():
    if not is_staging():
        raise RuntimeError(
            "Owner bootstrap is only for the isolated staging environment"
        )
    name = input("Your real name: ")
    email = input("Your email: ")
    password = getpass.getpass("Choose a password (12–128 characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise RuntimeError("Passwords do not match")
    data = Registration(name=name, email=email, password=password)
    with Session(engine()) as db:
        if db.scalar(select(Account).where(Account.email == data.email)):
            raise RuntimeError("That account already exists; no password was changed")
        db.add(
            Account(
                name=data.name,
                email=data.email,
                password_hash=hasher.hash(data.password),
            )
        )
        db.commit()
    print("Your Warehouse account was created. No inventory was seeded.")


if __name__ == "__main__":
    main()
