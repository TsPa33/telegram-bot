"""Fast, offline contract checks; no source database connection."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "local_vin_metadata_audit.py"
spec = importlib.util.spec_from_file_location("local_vin_metadata_audit", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Cursor:
    def __init__(self):
        self.query = ""
    def execute(self, query, args=None):
        assert query.strip().upper().startswith("SELECT")
        assert "information_schema" in query or "DATABASE()" in query
        assert args is None or args == ("td1q2018",)
        self.query = query
    def fetchone(self):
        return {"db": "td1q2018", "version": "8.4"}
    def fetchall(self):
        if "information_schema.COLUMNS" in self.query:
            return [
                {"table_name": "vin_dictionary", "column_name": "vin_code", "column_type": "varchar(17)", "column_key": "", "is_nullable": "YES"},
                {"table_name": "passanger_cars", "column_name": "id", "column_type": "int", "column_key": "PRI", "is_nullable": "NO"},
                {"table_name": "passanger_cars", "column_name": "motorcode", "column_type": "varchar(20)", "column_key": "", "is_nullable": "YES"},
            ]
        if "information_schema.TABLES" in self.query:
            return [{"table_name": "vin_dictionary", "estimated_rows": 6},
                    {"table_name": "passanger_cars", "estimated_rows": 110000}]
        if "information_schema.STATISTICS" in self.query:
            return [{"table_name": "vin_dictionary", "index_name": "PRIMARY", "seq_no": 1, "column_name": "vin_code"}]
        raise AssertionError("Unknown metadata request")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Connection:
    def cursor(self):
        return Cursor()


def test_metadata_audit_does_not_read_real_vins_or_data_rows():
    result = module.inventory(Connection())
    assert result["total_tables"] == 2
    assert result["vin_name_candidate_tables"] == 1
    assert result["tables"][1]["vin_candidate_fields"] == ["vin_code"]
    assert "VIN" in result["scope"]
    assert "vin_code" not in str(result["source_version"])


def test_candidate_names_are_not_evidence_of_vin_values():
    assert module.matches("vehicle_data", "model_id") == (False, True)
    assert module.matches("vin_dictionary", "vin_code") == (True, True)
    assert module.matches("passanger_cars", "motorcode") == (False, True)
