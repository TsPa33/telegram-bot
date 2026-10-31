"""Safety contract for the one-shot staging catalogue auditor."""
from pathlib import Path
import ast

SCRIPT = Path(__file__).resolve().parents[1] / "app" / "catalogue_audit_once.py"
STARTUP = Path(__file__).resolve().parents[1] / "app" / "staging.py"

def test_catalogue_audit_is_syntactically_valid_and_staging_gated():
    code = SCRIPT.read_text()
    ast.parse(code)
    assert 'WAREHOUSE_ENV' in code and 'staging' in code
    assert 'SET TRANSACTION READ ONLY' in code
    assert "connection.rollback()" in code
    assert 'with connection.begin_nested()' in code

def test_catalogue_audit_never_updates_or_creates_db_rows():
    code = SCRIPT.read_text()
    for operation in ('INSERT INTO ', 'UPDATE categories ', 'DELETE FROM ', 'TRUNCATE ', 'DROP TABLE ', 'ALTER TABLE ', 'session.add(', 'session.commit(', 'connection.commit()'):
        assert operation not in code
    assert 'password_hash' not in code
    assert 'select vin' not in code.lower()
    assert 'p.vin' not in code.lower()
    assert 'selling_price' not in code

def test_normal_startup_no_longer_runs_one_shot_auditor():
    code=STARTUP.read_text()
    assert 'audit_catalogue_readonly_once' not in code
    assert 'migrate(timeout)' in code
