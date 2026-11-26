#!/usr/bin/env bash
# Run on the existing Oracle host after prerequisites were verified.
# Optional --witness-id values are passed to the live read-only linkage probe.
# --verified-linkage-type 16 reuses confirmed linkage evidence for this host.
set -euo pipefail
umask 077

release=1eb06ddd39f5271fce437d84aa99944320af7822
service=carpot-oracle-adapter.service
directory=/opt/carpot/oracle-adapter
backup_root=/var/backups/carpot-oracle-adapter
dropin=/etc/systemd/system/carpot-oracle-adapter.service.d

if (( EUID != 0 )); then
    printf 'Run this installer with sudo on the Oracle Adapter host.\n' >&2
    exit 2
fi
if ! systemctl is-active --quiet "$service" || [[ ! -f $directory/app.py ]] ||
   [[ ! -x $directory/.venv/bin/python ]]; then
    printf 'Expected a running CarPot Oracle Adapter at %s.\n' "$directory" >&2
    exit 2
fi

temporary=$(mktemp -d /tmp/carpot-oracle-install.XXXXXX)
backup="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-${release:0:12}"
changed=0
cleanup() {
    status=$?
    trap - EXIT
    if (( status != 0 && changed )); then
        "$backup/rollback.sh" || printf 'Retry rollback with sudo %s/rollback.sh\n' "$backup" >&2
    fi
    rm -rf -- "$temporary"
    exit "$status"
}
trap cleanup EXIT

base="https://raw.githubusercontent.com/TsPa33/telegram-bot/$release/catalogue/oracle_adapter"
curl -fLsS --connect-timeout 10 --max-time 30 "$base/app.py" -o "$temporary/app.py"
curl -fLsS --connect-timeout 10 --max-time 30 "$base/check_source_graph.py" -o "$temporary/check_source_graph.py"
(
    cd "$temporary"
    sha256sum --check --strict <<'HASHES'
d716eca51854d65c32434a2e3fec993ec671e8f147dfaf8fbe5abc4f23a8511a  app.py
763bf48d55e85bc9e567822a79312ec78d2581af38719c4e9f092e484d1a9b23  check_source_graph.py
HASHES
)
python="$directory/.venv/bin/python"
"$python" -c 'import ast,pathlib,sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())' "$temporary/app.py"
if [[ ${1:-} == --verified-linkage-type ]]; then
    if [[ $# != 2 || ${2:-} != 16 ]]; then
        printf 'Use --verified-linkage-type 16 only after confirming the linkage on this host.\n' >&2
        exit 2
    fi
    commercial_type=16
    printf 'Reusing verified commercial linkage type 16.\n'
else
    pid=$(systemctl show "$service" -p MainPID --value)
    "$python" "$temporary/check_source_graph.py" linkage "$pid" "$@" | tee "$temporary/diagnosis.jsonl"
    commercial_type=$("$python" - "$temporary/diagnosis.jsonl" <<'PYTHON'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as report:
    result = next((row for row in map(json.loads, report)
                   if row.get("check") == "diagnostic_result"), {})
if result.get("ready_to_install") is not True or result.get("verified_commercial_linkage_type") != 16:
    raise SystemExit("Direct commercial linkage type 16 was not confirmed")
print(16)
PYTHON
    )
fi

install -d -m 0700 "$backup_root"
exec 9>"$backup_root/install.lock"
flock -n 9
mkdir -m 0700 "$backup"
cp -a -- "$directory/app.py" "$backup/app.py"
for name in 99-carpot-stage13-linkage.conf stage13-linkage.env; do
    if [[ -f $dropin/$name ]]; then
        cp -a -- "$dropin/$name" "$backup/$name"
    fi
done
cat > "$backup/rollback.sh" <<'ROLLBACK'
#!/usr/bin/env bash
set -euo pipefail
backup=$(dirname -- "$(readlink -f -- "$0")")
app=/opt/carpot/oracle-adapter/app.py
dropin=/etc/systemd/system/carpot-oracle-adapter.service.d
cp -a -- "$backup/app.py" "$app.rollback"
mv -f -- "$app.rollback" "$app"
for name in 99-carpot-stage13-linkage.conf stage13-linkage.env; do
    if [[ -f $backup/$name ]]; then
        cp -a -- "$backup/$name" "$dropin/$name"
    else
        rm -f -- "$dropin/$name"
    fi
done
systemctl daemon-reload
systemctl restart carpot-oracle-adapter.service
systemctl is-active carpot-oracle-adapter.service
ROLLBACK
chmod 0700 "$backup/rollback.sh"
ln -sfn -- "$backup" "$backup_root/latest-stage13"
printf 'Backup: %s\n' "$backup"

changed=1
if [[ ! -d $dropin ]]; then
    install -d -m 0755 "$dropin"
fi
printf 'ORACLE_COMMERCIAL_LINKAGE_TYPE=%s\n' "$commercial_type" > "$temporary/linkage.env"
printf '[Service]\nEnvironmentFile=%s/stage13-linkage.env\n' "$dropin" > "$temporary/linkage.conf"
install -m 0600 "$temporary/linkage.env" "$dropin/stage13-linkage.env"
install -m 0644 "$temporary/linkage.conf" "$dropin/99-carpot-stage13-linkage.conf"
cp -a -- "$directory/app.py" "$directory/app.py.stage13-new"
cat "$temporary/app.py" > "$directory/app.py.stage13-new"
mv -f -- "$directory/app.py.stage13-new" "$directory/app.py"

systemctl daemon-reload
systemctl restart "$service"
for attempt in {1..15}; do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8081/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
systemctl is-active "$service"
pid=$(systemctl show "$service" -p MainPID --value)
"$directory/.venv/bin/python" -c '
import pathlib, sys
actual = pathlib.Path(f"/proc/{int(sys.argv[1])}/environ").read_bytes().split(b"\0")
expected = b"ORACLE_COMMERCIAL_LINKAGE_TYPE=" + sys.argv[2].encode("ascii")
if expected not in actual:
    raise SystemExit("The running service is missing the verified linkage type")
' "$pid" "$commercial_type"
"$directory/.venv/bin/python" "$temporary/check_source_graph.py" verify "$pid"
changed=0
printf 'Installed adapter commit %s\n' "$release"
