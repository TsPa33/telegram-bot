"""Offline acceptance for read-only OEM binding classification; no staging SQL."""
from types import SimpleNamespace
from app.services import oem_stage8_gap_audit as gap


def row(*, source="manual", car=107555, product_id=188, canonical_id=None):
    return SimpleNamespace(id="row-1", included=True, status="planned",
        assembly_consumed_operation_id=None, name="Генератор",
        category_name="Підвіска", subcategory_name="Тест",
        source=source, catalog_key=f"car:{car}:product:{product_id}",
        plan_v3={"canonical_part_type_id": canonical_id} if canonical_id else {})


def test_generic_name_is_review_only_not_auto_selected(monkeypatch):
    monkeypatch.setattr(gap, "valid_reference", lambda *_: False)
    product = {"product_id": 188, "kind": "part", "article_count": 3,
               "name_uk": "Генератор", "candidate_aliases": ["Генератор"],
               "pilot_reviewed": True}
    result = gap.summarize([row()], {188: product}, {}, 107555, {}, object())
    assert result["counts"]["included_rows"] == 1
    assert result["counts"].get("mapped_source_prd", 0) == 0
    assert result["counts"]["no_verified_source_prd_binding"] == 1
    assert result["unmatched_examples"][0]["review_only_product_ids"] == [188]
    assert result["unmatched_examples"][0]["not_fitment_verified"] is True


def test_exact_source_prd_is_mapped_and_stale_modification_is_not(monkeypatch):
    monkeypatch.setattr(gap, "valid_reference", lambda *_: False)
    p = {188: {"product_id": 188, "kind": "review", "article_count": 1}}
    good = gap.summarize([row(source="carpot.catalogue.v1")], p, {}, 107555, {}, object())
    assert good["counts"]["mapped_source_prd"] == 1
    assert good["counts"].get("unmatched_source_prd", 0) == 0
    stale = gap.summarize([row(source="carpot.catalogue.v1", car=107556)],
                          p, {}, 107555, {}, object())
    assert stale["counts"]["stale_modification_prd_key"] == 1


def test_unproven_canonical_mapping_is_never_taken_as_oem_fitment(monkeypatch):
    monkeypatch.setattr(gap, "valid_reference", lambda *_: False)
    result = gap.summarize([row(canonical_id="legacy")], {}, {}, 107555, {}, object())
    assert result["counts"]["canonical_without_source_prd_proof"] == 1
    assert result["counts"]["mapped_source_prd"] == 0


def test_live_stage7_matcher_compatibility_no_stage8_deploy(monkeypatch):
    """Legacy matcher accepts only three arguments; source gate is preserved."""
    monkeypatch.setattr(gap, "valid_reference", lambda *_: False)
    product = {188: {"product_id": 188, "kind": "part", "article_count": 3}}
    monkeypatch.setattr(
        gap, "runtime_matches", lambda r, products, bindings: products.get(188)
    )
    stale = gap.summarize(
        [row(source="carpot.catalogue.v1", car=999999)],
        product, {}, 107555, {}, object()
    )
    assert stale["counts"]["stale_modification_prd_key"] == 1
    exact = gap.summarize(
        [row(source="carpot.catalogue.v1", car=107555)],
        product, {}, 107555, {}, object()
    )
    assert exact["counts"]["mapped_source_prd"] == 1


def test_live_stage7_fallback_does_not_promote_manual_or_unlinked(monkeypatch):
    monkeypatch.setattr(gap, "valid_reference", lambda *_: False)
    monkeypatch.setattr(gap, "runtime_matches", lambda r, products, bindings: None)
    product = {188: {"product_id": 188, "kind": "review", "article_count": 1}}
    exact = gap.summarize(
        [row(source="carpot.catalogue.v1")],
        product, {}, 107555, {}, object()
    )
    assert exact["counts"]["mapped_source_prd"] == 1
    manual = gap.summarize([row(source="manual")], product, {}, 107555, {}, object())
    assert manual["counts"]["mapped_source_prd"] == 0
    product[188]["article_count"] = 0
    empty = gap.summarize(
        [row(source="carpot.catalogue.v1")], product, {}, 107555, {}, object()
    )
    assert empty["counts"]["mapped_source_prd"] == 0
