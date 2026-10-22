"""Offline checksum + full archive decode. Never connects to a database."""
import argparse
import hashlib
import hmac
import os
from pathlib import Path
import re
import subprocess
import sys


def verify(archive: Path, docker: bool = False, docker_config: str | None = None):
    archive = archive.absolute()
    checksum = archive.with_name(archive.name + ".sha256")
    if archive.is_symlink() or checksum.is_symlink():
        raise ValueError("Symlink backup paths are not allowed")
    if not archive.is_file() or not checksum.is_file():
        raise ValueError("Archive and adjacent .sha256 file are required")
    if os.name == "posix" and archive.stat().st_mode & 0o077:
        raise ValueError("Backup must be private; chmod 600 the archive")
    line = checksum.read_text(encoding="ascii")
    match = re.fullmatch(r"([a-f0-9]{64})  ([^/\\\r\n]+)\n?", line)
    if not match or match[2] != archive.name:
        raise ValueError("Invalid checksum sidecar or filename")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Not a PostgreSQL custom-format dump")
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if not hmac.compare_digest(digest.hexdigest(), match[1]):
        raise ValueError("SHA-256 mismatch")
    if docker:
        command = ["docker"] + (["--config", docker_config] if docker_config else [])
        command += ["run", "--rm", "--network", "none", "--mount",
                   f"type=bind,src={archive.parent},dst=/backup,readonly",
                   "--entrypoint", "pg_restore", "postgres:16-alpine"]
        source = "/backup/" + archive.name
    else:
        command = ["pg_restore"]
        source = str(archive)
    for options in (["--list"], ["--no-owner", "--no-acl", "--file=" + os.devnull]):
        result = subprocess.run(command + options + [source], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        if result.returncode:
            raise ValueError("pg_restore archive validation failed; diagnostics suppressed")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--docker", action="store_true", help="Use PostgreSQL 16 tools in a network-isolated Docker container")
    parser.add_argument("--docker-config", help="Optional Docker CLI configuration directory")
    args = parser.parse_args()
    try:
        digest = verify(args.archive, args.docker, args.docker_config)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Backup verification failed. Check private file permissions, SHA-256 sidecar and PostgreSQL 16 tools.", file=sys.stderr)
        return 1
    print("PASS: SHA-256, custom format, pg_restore --list and full archive decode. SHA-256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
