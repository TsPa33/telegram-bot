"""Optional BuildKit helper for this cloud's host-only proxy DNS and trusted CA.

Ordinary local machines should use `docker compose up --build` instead.
No proxy credentials or CA files are written into the checkout/image.
"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "component", choices=["backend", "frontend", "staging-backend", "staging-frontend"]
)
parser.add_argument(
    "--ca", type=Path, default=Path("/etc/ssl/certs/ca-certificates.crt")
)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
if not args.ca.is_file():
    parser.error("Provide a trusted CA bundle with --ca; TLS verification is mandatory")
command = [
    "docker",
    "build",
    "--network",
    "host",
    "--build-arg",
    "HTTP_PROXY",
    "--build-arg",
    "HTTPS_PROXY",
    "--build-arg",
    "NO_PROXY",
    "--secret",
    "id=warehouse_ca,src=" + str(args.ca.resolve()),
]
for host in {
    urlsplit(os.environ[k]).hostname
    for k in ("HTTP_PROXY", "HTTPS_PROXY")
    if os.environ.get(k)
}:
    if host:
        command.extend(["--add-host", host + ":" + socket.gethostbyname(host)])
command.extend(["-t", "carpot-warehouse-" + args.component])
if args.component == "backend":
    command.extend(["-t", "carpot-warehouse-tests"])
if args.component.startswith("staging-"):
    component = args.component.removeprefix("staging-")
    command.extend(
        [
            "--file",
            str(root / "deploy/railway" / (component + ".Dockerfile")),
            str(root),
        ]
    )
else:
    command.append(str(root / args.component))
env = dict(os.environ)
# Do not require writing the cloud machine's read-only home directory.
env.setdefault(
    "DOCKER_CONFIG", str(Path(tempfile.gettempdir()) / "warehouse-docker-config")
)
env.setdefault("BUILDX_CONFIG", str(Path(tempfile.gettempdir()) / "warehouse-buildx"))
result = subprocess.run(
    command,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    timeout=300,
)
output = result.stdout
for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
    if os.environ.get(key):
        output = output.replace(os.environ[key], "<configured proxy>")
print(output)
raise SystemExit(result.returncode)
