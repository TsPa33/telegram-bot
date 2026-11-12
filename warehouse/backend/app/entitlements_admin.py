"""Local-only pilot dry-run/enrollment. No production or staging activation path."""

import argparse, json
from sqlalchemy.orm import Session
from app.db import engine
from app.services import entitlements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace")
    parser.add_argument(
        "--mode", choices=["compatibility", "dry_run", "enforce"], default="dry_run"
    )
    args = parser.parse_args()
    if not entitlements.enabled():
        raise RuntimeError("Only explicitly enabled loopback *_test DB is allowed")
    with Session(engine()) as db:
        result = entitlements.configure_workspace(db, args.workspace, args.mode)
        db.commit()
        print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
