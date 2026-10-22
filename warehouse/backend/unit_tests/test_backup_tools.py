import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("variables,flag", [
    ({}, "--confirm-warehouse-staging"),
    ({"RAILWAY_ENVIRONMENT_NAME":"production"}, "--confirm-warehouse-staging"),
    ({"RAILWAY_ENVIRONMENT_NAME":"warehouse-staging","WAREHOUSE_DB_HOST":"public.example.test"}, "--confirm-warehouse-staging"),
    ({"RAILWAY_ENVIRONMENT_NAME":"warehouse-staging","WAREHOUSE_DB_HOST":"public.example.test,warehouse-db.railway.internal"}, "--confirm-warehouse-staging"),
    ({"RAILWAY_ENVIRONMENT_NAME":"warehouse-staging","WAREHOUSE_DB_HOST":"public.example.test,other\nwarehouse-db.railway.internal"}, "--confirm-warehouse-staging"),
    ({"RAILWAY_ENVIRONMENT_NAME":"warehouse-staging"}, "--local-test"),
    ({"RAILWAY_PROJECT_ID":"any-project"}, "--local-test"),
    ({"WAREHOUSE_DB_HOST":"127.0.0.1","WAREHOUSE_DB_NAME":"warehouse_staging"}, "--local-test"),
    ({"WAREHOUSE_DB_HOST":"public.example.test","WAREHOUSE_DB_NAME":"warehouse_test"}, "--local-test"),
    ({"WAREHOUSE_DB_HOST":"127.0.0.1","WAREHOUSE_DB_NAME":"carpot_prod_test"}, "--local-test"),
])
def test_unsafe_targets_are_rejected_before_database_tools(variables, flag):
    env = {k:v for k,v in os.environ.items() if not k.startswith(("RAILWAY_","WAREHOUSE_"))}
    env.update(variables)
    result = subprocess.run(["sh",str(SCRIPTS / "backup-staging.sh"),flag],env=env,capture_output=True,text=True)
    assert result.returncode != 0
    assert "password" not in result.stdout.lower()


def test_remote_command_uses_existing_service_and_no_literal_credentials():
    tool = load("backup-railway")
    args, source = tool.command("reviewed-project-id")
    assert args[:2] == ["railway","ssh"]
    assert args[args.index("--environment")+1] == "warehouse-staging"
    assert args[args.index("--service")+1] == "postgres"
    assert '[ "${RAILWAY_PROJECT_ID:-}" = \'reviewed-project-id\' ]' in source
    assert '[ "${RAILWAY_SERVICE_NAME:-}" = \'postgres\' ]' in source
    assert "${POSTGRES_PASSWORD:-}" in source
    assert not any(word in args for word in ("up","deploy","run","variables"))
    with pytest.raises(ValueError):
        tool.command("https://user:password@example.test", "postgres")


def test_checksum_verification_and_full_decode_commands(tmp_path, monkeypatch):
    tool = load("verify-backup")
    archive = tmp_path / "warehouse-staging.dump"
    archive.write_bytes(b"PGDMPsynthetic-test-only")
    archive.chmod(0o600)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name+".sha256").write_text(digest+"  "+archive.name+"\n")
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(tool.subprocess,"run",run)
    assert tool.verify(archive) == digest
    assert calls == [["pg_restore","--list",str(archive)],
                     ["pg_restore","--no-owner","--no-acl","--file="+os.devnull,str(archive)]]
    archive.write_bytes(b"PGDMPcorrupted-test-only")
    with pytest.raises(ValueError,match="SHA-256"):
        tool.verify(archive)
    assert len(calls) == 2


def test_bad_permissions_and_archive_errors_fail_closed(tmp_path, monkeypatch):
    tool = load("verify-backup")
    archive = tmp_path / "warehouse-staging.dump"
    archive.write_bytes(b"PGDMPsynthetic-test-only")
    archive.chmod(0o644)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name+".sha256").write_text(digest+"  "+archive.name+"\n")
    with pytest.raises(ValueError,match="private"):
        tool.verify(archive)
    archive.chmod(0o600)
    monkeypatch.setattr(tool.subprocess,"run",lambda args,**kwargs:subprocess.CompletedProcess(args,1))
    with pytest.raises(ValueError,match="archive validation"):
        tool.verify(archive)


@pytest.mark.parametrize("check_only", [False,True])
def test_pg_dump_failure_and_preflight_do_not_leak_credentials(tmp_path,check_only):
    tools = tmp_path / "tools"
    tools.mkdir()
    commands = {
        "pg_dump": 'if [ "$1" = --version ]; then echo "pg_dump (PostgreSQL) 16.1"; else echo "$PGPASSWORD" >&2; exit 1; fi',
        "pg_restore": 'echo "pg_restore (PostgreSQL) 16.1"',
        "psql": 'if [ "$1" = --version ]; then echo "psql (PostgreSQL) 16.1"; else case "$*" in *server_version_num*) echo 160001;; *) echo f482ab1376c0;; esac; fi',
    }
    for name, code in commands.items():
        path = tools / name
        path.write_text("#!/bin/sh\n"+code+"\n")
        path.chmod(0o755)
    env = dict(os.environ,PATH=str(tools)+os.pathsep+os.environ["PATH"],
               RAILWAY_ENVIRONMENT_NAME="warehouse-staging",WAREHOUSE_DB_HOST="warehouse-db.railway.internal",
               WAREHOUSE_DB_NAME="warehouse_staging",WAREHOUSE_DB_USER="warehouse_staging",
               WAREHOUSE_DB_PASSWORD="synthetic-never-log-this")
    env["WAREHOUSE_BACKUP_CHECK_ONLY"]="true" if check_only else "false"
    env.pop("WAREHOUSE_DATABASE_URL",None)
    before = set(Path("/tmp").glob("warehouse-backup.*"))
    result = subprocess.run(["sh",str(SCRIPTS / "backup-staging.sh"),"--confirm-warehouse-staging"],env=env,capture_output=True,text=True)
    assert (result.returncode == 0) is check_only
    if check_only:assert "No pg_dump executed" in result.stdout
    assert "synthetic-never-log-this" not in result.stdout+result.stderr
    assert set(Path("/tmp").glob("warehouse-backup.*")) == before


def transfer_frame(payload=b"PGDMP"+bytes(range(256))*8):
    import base64
    lines=[b"CLI notice",b"WAREHOUSE_BACKUP_BASE64_V1",b"DIRECTORY /tmp/warehouse-backup.12345678"]
    for name,data in (("warehouse-staging.dump",payload),("source-revision.txt",b"offline_fixture\n")):
        lines.append(f"FILE {name} {len(data)} {hashlib.sha256(data).hexdigest()}".encode())
        lines.extend(base64.encodebytes(data).splitlines())
        lines.append(b"END_FILE")
    lines.append(b"END_WAREHOUSE_BACKUP_BASE64_V1")
    return b"\n".join(lines)+b"\n"


@pytest.mark.parametrize("crlf", [False,True])
def test_framed_transfer_preserves_all_byte_values(tmp_path, crlf):
    import io
    tool=load("backup-railway")
    data=b"PGDMP"+bytes(range(256))*8192
    # Build a frame independently of the decoder.
    frame=transfer_frame(data)
    if crlf:frame=frame.replace(b"\n",b"\r\n")
    assert tool.receive(io.BytesIO(frame),tmp_path)=="/tmp/warehouse-backup.12345678"
    assert (tmp_path/"warehouse-staging.dump").read_bytes()==data
    assert (tmp_path/"warehouse-staging.dump").stat().st_mode & 0o077 == 0
    assert (tmp_path/"warehouse-staging.dump.sha256").read_text().startswith(hashlib.sha256(data).hexdigest())


@pytest.mark.parametrize("failure", ["checksum","truncated","name","size","trailing"])
def test_download_rejects_corrupt_or_incomplete_cli_output(tmp_path,failure):
    import base64
    import sys
    tool=load("backup-railway")
    frame=transfer_frame()
    if failure=="checksum":frame=frame.replace(hashlib.sha256(b"PGDMP"+bytes(range(256))*8).hexdigest().encode(),b"0"*64)
    if failure=="truncated":frame=frame[:-20]
    if failure=="name":frame=frame.replace(b"FILE warehouse-staging.dump",b"FILE ../../private.dump")
    if failure=="size":frame=frame.replace(b"FILE warehouse-staging.dump 2053",b"FILE warehouse-staging.dump 2052")
    if failure=="trailing":frame+=b"unexpected output\n"
    program="import sys,base64;sys.stdin.buffer.read();sys.stdout.buffer.write(base64.b64decode("+repr(base64.b64encode(frame).decode())+"))"
    destination=tmp_path/"received"
    with pytest.raises(ValueError):
        tool.download([sys.executable,"-c",program],"non-secret-script",destination)
    assert not destination.exists()


def test_fetch_never_redumps_and_preflight_is_explicit():
    tool=load("backup-railway")
    _,source=tool.command("reviewed-project-id",transfer=True,fetch_directory="/tmp/warehouse-backup.12345678")
    assert "pg_dump" not in source
    assert "base64" in source
    _,source=tool.command("reviewed-project-id",preflight=True,database="warehouse_staging")
    assert "export WAREHOUSE_BACKUP_CHECK_ONLY=true" in source
    assert "export WAREHOUSE_DB_NAME='warehouse_staging'" in source
    with pytest.raises(ValueError):tool.command("reviewed-project-id",preflight=True,transfer=True)
    with pytest.raises(ValueError):tool.command("reviewed-project-id",database="railway")


def test_download_refuses_existing_directory(tmp_path):
    tool=load("backup-railway")
    with pytest.raises(FileExistsError):tool.download(["not-a-command"],"unused",tmp_path)


@pytest.mark.parametrize("variable,value", [("RAILWAY_PROJECT_ID","wrong-project"),("RAILWAY_ENVIRONMENT_NAME","production"),("RAILWAY_SERVICE_NAME","warehouse-db")])
def test_remote_identity_mismatch_fails_before_fetch(variable,value):
    tool=load("backup-railway")
    _,source=tool.command("reviewed-project-id",transfer=True,fetch_directory="/tmp/warehouse-backup.12345678")
    env=dict(os.environ,RAILWAY_PROJECT_ID="reviewed-project-id",RAILWAY_ENVIRONMENT_NAME="warehouse-staging",RAILWAY_SERVICE_NAME="postgres")
    env[variable]=value
    result=subprocess.run(["sh","-s"],input=source,text=True,env=env,capture_output=True)
    assert result.returncode != 0
    assert "WAREHOUSE_BACKUP_BASE64_V1" not in result.stdout


def test_valid_transfer_with_failed_command_is_not_accepted(tmp_path):
    import base64
    import sys
    tool=load("backup-railway")
    program="import sys,base64;sys.stdin.buffer.read();sys.stdout.buffer.write(base64.b64decode("+repr(base64.b64encode(transfer_frame()).decode())+"));sys.exit(1)"
    destination=tmp_path/"received"
    with pytest.raises(ValueError):tool.download([sys.executable,"-c",program],"non-secret-script",destination)
    assert not destination.exists()
