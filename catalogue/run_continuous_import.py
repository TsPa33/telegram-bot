"""Run CarPot Catalogue selective migration continuously from Windows.

Keeps both source and Railway SSH tunnel connections outside this process.
Resumes via atomic destination-side checkpoints already implemented by importers.
Stops on errors, database size guard, or exhausted source; no silent retries.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PHASES = (
    ("articles", "full_import.py", 200000, "--max-rows", "SOURCE EXHAUSTED"),
    ("oem", "oem_indexed_import.py", 20000, "--max-articles", "SOURCE EXHAUSTED"),
)

def execute(phase, filename, batch_limit, limit_arg, done_text, size_limit):
    script = ROOT / filename
    if not script.is_file():
        raise RuntimeError(f"Missing {script.name}. Download it from the same GitHub branch.")
    command = [
        sys.executable, "-u", str(script),
        limit_arg, str(batch_limit),
        "--max-db-mib", str(size_limit),
        "--confirm-staging",
    ]
    command.extend(["--batch-size", "500"] if phase == "articles"
                   else ["--batch-articles", "100"])
    print(f"\n[{phase}] Starting next resumable segment", flush=True)
    result = subprocess.Popen(
        command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    exhausted = False
    try:
        for line in result.stdout:
            print(line, end="", flush=True)
            if done_text in line:
                exhausted = True
        status = result.wait()
    except KeyboardInterrupt:
        result.terminate()
        try:
            result.wait(timeout=10)
        except subprocess.TimeoutExpired:
            result.kill()
            result.wait()
        raise
    if status != 0:
        raise RuntimeError(f"{phase} stopped with exit code {status}; no more runs scheduled")
    return exhausted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "articles", "oem"), default="all")
    parser.add_argument("--max-db-mib", type=int, default=2000,
                        help="Conservative MySQL data+index metadata guard (not physical Railway disk)")
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()
    if not args.confirm_staging:
        parser.error("--confirm-staging is required")
    if not 100 <= args.max_db_mib <= 3000:
        parser.error("max-db-mib must be between 100 and 3000 for the current 5GB volume")
    if os.getenv("DEST_DATABASE") not in ("railway", "catalogue"):
        parser.error("DEST_DATABASE must be an isolated staging database")
    if os.getenv("DEST_HOST") not in ("127.0.0.1", "localhost"):
        parser.error("Use the Railway local SSH tunnel, not a public database endpoint")
    if os.getenv("DEST_PORT") == os.getenv("SOURCE_PORT", "3306"):
        parser.error("Local MySQL and Railway tunnel ports must differ")
    selected = [p for p in PHASES if args.phase in ("all", p[0])]
    print("CarPot Catalogue continuous import: local source SELECT only; Railway staging writes.", flush=True)
    print("Keep Windows awake, local MySQL and Railway SSH tunnel running.", flush=True)
    for phase, filename, batch_limit, limit_arg, done_text in selected:
        while True:
            finished = execute(phase, filename, batch_limit, limit_arg,
                               done_text, args.max_db_mib)
            if finished:
                print(f"COMPLETED {phase}: source exhausted.", flush=True)
                break
            print(f"[{phase}] Batch limit reached; continuing from Railway checkpoint.", flush=True)
    print("ALL SELECTED PHASES COMPLETED. Verify counts and disk usage in Railway.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user. Saved checkpoints remain in Railway.", flush=True)
        sys.exit(130)
    except Exception as exc:
        print(f"STOPPED SAFELY: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
