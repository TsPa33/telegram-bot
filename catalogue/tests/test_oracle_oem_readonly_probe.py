"""Offline safety tests; no database/network access."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracle_oem_readonly_probe as audit


def test_index_prefix_requires_leftmost_columns():
    idx = {"article_oe": {"ix": ["supplierId", "DataSupplierArticleNumber"]}}
    assert audit.prefix_index(idx, "article_oe", ("supplierid",))
    assert not audit.prefix_index(idx, "article_oe", ("manufacturerid",))


def test_incomplete_tables_are_excluded():
    assert set(audit.TABLES).isdisjoint(audit.DEFERRED)


def test_readiness_fails_closed_without_indexes():
    cols = {"article_oe": ["supplierId", "DataSupplierArticleNumber", "manufacturerId", "OENbr"]}
    assert not audit.readiness(cols, {})["oem_lookup"]


def test_quote_rejects_sql_injection():
    with pytest.raises(ValueError):
        audit.quote("x; DROP TABLE users")
    assert audit.quote("article_oe") == chr(96) + "article_oe" + chr(96)
