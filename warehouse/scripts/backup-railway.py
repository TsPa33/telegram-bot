"""One-off backup/fetch via authenticated Railway SSH; no raw binary terminal I/O."""
import argparse
import base64
import hashlib
import hmac
from pathlib import Path
import re
import shutil
import subprocess
import sys

MAGIC = b"WAREHOUSE_BACKUP_BASE64_V1"
END = b"END_WAREHOUSE_BACKUP_BASE64_V1"
FILES = ("warehouse-staging.dump", "source-revision.txt")
MAX_BYTES = 5 * 1024 * 1024 * 1024


def command(project: str, service: str = "postgres", *, database=None, preflight=False,
            transfer=False, fetch_directory=None):
    for value in (project, service):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Use project ID and service NAME, not URLs")
    if database is not None and not re.fullmatch(r"(?:warehouse|carpot_warehouse)[A-Za-z0-9_-]*", database):
        raise ValueError("Use the verified Warehouse database name")
    if fetch_directory and not re.fullmatch(r"/tmp/warehouse-backup\.[A-Za-z0-9]{8}", fetch_directory):
        raise ValueError("Invalid temporary backup directory")
    if (fetch_directory and not transfer) or (preflight and (transfer or fetch_directory)):
        raise ValueError("Invalid preflight/transfer combination")
    prefix = '''set +x
set -eu
[ "${RAILWAY_PROJECT_ID:-}" = EXPECTED_PROJECT ] || exit 1
[ "${RAILWAY_ENVIRONMENT_NAME:-}" = warehouse-staging ] || exit 1
[ "${RAILWAY_SERVICE_NAME:-}" = EXPECTED_SERVICE ] || exit 1
# Process-local aliases only; no Railway Variables are created or modified.
export WAREHOUSE_DB_HOST="${WAREHOUSE_DB_HOST:-${RAILWAY_PRIVATE_DOMAIN:-}}"
export WAREHOUSE_DB_PORT="${WAREHOUSE_DB_PORT:-${PGPORT:-5432}}"
export WAREHOUSE_DB_NAME="${WAREHOUSE_DB_NAME:-${POSTGRES_DB:-}}"
export WAREHOUSE_DB_USER="${WAREHOUSE_DB_USER:-${POSTGRES_USER:-}}"
export WAREHOUSE_DB_PASSWORD="${WAREHOUSE_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
'''.replace("EXPECTED_SERVICE", "'" + service + "'").replace("EXPECTED_PROJECT", "'" + project + "'")
    if database:
        prefix += "export WAREHOUSE_DB_NAME='" + database + "'\n"
    prefix += "export WAREHOUSE_BACKUP_CHECK_ONLY=" + ("true" if preflight else "false") + "\n"
    if fetch_directory:
        source = prefix + "directory='" + fetch_directory + "'\n"
    else:
        source = prefix + Path(__file__).with_name("backup-staging.sh").read_text()
    if transfer:
        source += '''
command -v base64 >/dev/null 2>&1 || exit 1
[ -d "$directory" ] && [ ! -L "$directory" ] || exit 1
cd "$directory"
for file in warehouse-staging.dump source-revision.txt; do
  [ -f "$file" ] && [ ! -L "$file" ] || exit 1
done
sha256sum -c warehouse-staging.dump.sha256 source-revision.txt.sha256 >/dev/null 2>&1 || exit 1
printf '%s\\n' WAREHOUSE_BACKUP_BASE64_V1
printf 'DIRECTORY %s\\n' "$directory"
for file in warehouse-staging.dump source-revision.txt; do
  size=$(wc -c < "$file" | tr -d '[:space:]')
  digest=$(sha256sum "$file" | awk '{print $1}')
  printf 'FILE %s %s %s\\n' "$file" "$size" "$digest"
  base64 "$file"
  printf '%s\\n' END_FILE
done
printf '%s\\n' END_WAREHOUSE_BACKUP_BASE64_V1
'''
    args = ["railway", "ssh", "--project", project, "--environment", "warehouse-staging",
            "--service", service, "--", "sh", "-s", "--", "--confirm-warehouse-staging"]
    return args, source


def receive(stream, destination: Path):
    """Decode bounded ASCII frames; accept only exact size, digest and filenames."""
    def line():
        value = stream.readline(4097)
        if not value or len(value) > 4096 or not value.endswith(b"\n"):
            raise ValueError("Truncated or oversized transfer line")
        return value.rstrip(b"\r\n")
    for _ in range(64):
        if line() == MAGIC:
            break
    else:
        raise ValueError("Backup transfer marker missing")
    directory = line()
    if not re.fullmatch(rb"DIRECTORY /tmp/warehouse-backup\.[A-Za-z0-9]{8}", directory):
        raise ValueError("Invalid remote directory")
    for name in FILES:
        match = re.fullmatch(rb"FILE ([a-z.-]+) ([0-9]{1,12}) ([a-f0-9]{64})", line())
        if not match or match[1].decode() != name:
            raise ValueError("Unexpected artifact name or metadata")
        size = int(match[2])
        limit = MAX_BYTES if name.endswith(".dump") else 4096
        if not 0 < size <= limit:
            raise ValueError("Invalid artifact size")
        digest = hashlib.sha256()
        count = 0
        part = destination / (name + ".part")
        with part.open("xb") as output:
            part.chmod(0o600)
            while True:
                encoded = line()
                if encoded == b"END_FILE":
                    break
                if not encoded:
                    raise ValueError("Empty payload line")
                decoded = base64.b64decode(encoded, validate=True)
                count += len(decoded)
                if count > size:
                    raise ValueError("Artifact exceeds declared size")
                digest.update(decoded)
                output.write(decoded)
        if count != size or not hmac.compare_digest(digest.hexdigest(), match[3].decode()):
            raise ValueError("Transfer SHA-256 or size mismatch")
        if name.endswith(".dump"):
            with part.open("rb") as check:
                if check.read(5) != b"PGDMP":
                    raise ValueError("Not a custom-format PostgreSQL backup")
        sidecar = destination / (name + ".sha256")
        with sidecar.open("x", encoding="ascii") as output:
            sidecar.chmod(0o600)
            output.write(digest.hexdigest() + "  " + name + "\n")
    if line() != END or stream.read(1):
        raise ValueError("Incomplete transfer or unexpected trailing output")
    for name in FILES:
        (destination / (name + ".part")).rename(destination / name)
    return directory.decode().split(" ",1)[1]


def download(invocation, source, destination: Path):
    destination = destination.expanduser().absolute()
    repository = Path(__file__).resolve().parents[2]
    if destination.resolve().is_relative_to(repository):
        raise ValueError("Backup destination must be outside the Git repository")
    destination.mkdir(mode=0o700)
    process = None
    try:
        process = subprocess.Popen(invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        process.stdin.write(source.encode())
        process.stdin.close()
        remote = receive(process.stdout, destination)
        if process.wait() != 0:
            raise ValueError("Railway SSH command failed")
        return destination, remote
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        shutil.rmtree(destination)
        raise
    finally:
        if process is not None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Explicit existing Railway project ID")
    parser.add_argument("--service", default="postgres", help="Existing DB service NAME; default postgres")
    parser.add_argument("--database", help="Verified WAREHOUSE_DB_NAME; process-only override if POSTGRES_DB differs")
    parser.add_argument("--confirm", required=True, choices=["warehouse-staging"])
    parser.add_argument("--preflight", action="store_true", help="Read-only metadata/version/revision checks; no pg_dump")
    parser.add_argument("--download-to", type=Path, help="NEW private local directory outside repository")
    parser.add_argument("--fetch-directory", help="Retrieve an existing /tmp backup; no new pg_dump")
    args = parser.parse_args()
    try:
        invocation, source = command(args.project, args.service, database=args.database,
                                     preflight=args.preflight, transfer=bool(args.download_to),
                                     fetch_directory=args.fetch_directory)
        if args.download_to:
            destination, remote = download(invocation, source, args.download_to)
            print("PASS: private local files received with matching size and SHA-256:", destination)
            print("Remote backup retained for restore verification and explicit cleanup:", remote)
            print("Next: run verify-backup.py and restore ONLY to isolated test PostgreSQL.")
            return 0
        return subprocess.run(invocation, input=source, text=True).returncode
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Backup command failed. No final download accepted; check CLI access, target, tools and destination. Remote temporary files may remain. Raw output suppressed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
