"""Stage 8: exact PRD provenance can yield cross-reference, never implied VIN fitment."""
from types import SimpleNamespace
from app.services.auto_oem import matches


def row(car, pid, *, source="carpot.catalogue.v1"):
    return SimpleNamespace(
        source=source, catalog_key=f"car:{car}:product:{pid}",
        plan_v3={}, name="Тестова запчастина",
        category_name="A", subcategory_name="B")


def test_exact_modification_source_review_type_can_receive_cross_reference():
    product = dict(product_id=188, kind="review", article_count=2)
    assert matches(row(107555, 188), {188: product},
                   source_modification_id=107555) is product
    # The only allowed provenance is an exact source row for this modification.
    assert matches(row(107556, 188), {188: product},
                   source_modification_id=107555) is None


def test_empty_source_review_and_unrelated_modification_never_get_oem():
    p = {188: dict(product_id=188, kind="review", article_count=0)}
    assert matches(row(107555, 188), p, source_modification_id=107555) is None
    p[188]["article_count"] = 1
    assert matches(row(107555, 188, source="manual"), p,
                   source_modification_id=107555) is None
    assert matches(row(107555, 188), p,
                   source_modification_id=126480) is None


def test_reviewed_product_rejects_stale_source_modification_even_same_prd():
    p = {188: dict(product_id=188, kind="part", article_count=1)}
    assert matches(row(107555, 188), p, source_modification_id=107555) == p[188]
    assert matches(row(107556, 188), p, source_modification_id=107555) is None


def test_unbound_generic_row_is_not_promoted_through_name_similarity():
    p = {188: dict(product_id=188, kind="review", article_count=12,
                   name_uk="Тестова запчастина", candidate_aliases=["Тестова запчастина"])}
    assert matches(row(107555, 188, source="manual"), p,
                   source_modification_id=107555) is None
