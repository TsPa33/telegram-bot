from oracle_source_graph import project


def test_projects_prd_types_and_uses_exact_supplier_articles_once():
    identity = dict(kind="commercial", manufacturer_id=11, model_id=12, car_id=1)
    data = {"identity": identity, "status": "available",
            "modification": {**identity, "description": "Test", "construction_interval": None},
            "articles": [[2, "A", "Exact supplier", ["OE"]], [2, "a", "Exact supplier", []]],
            "links": {"5": [0, 1]}, "products": [
                {"product_id": 5, "node_ids": [99, 101], "descriptions": [
                    {"id": 5, "description": "Bracket", "assemblygroupdescription": "Axle"}]},
                {"product_id": 7, "node_ids": [100], "descriptions": [
                    {"id": 7, "description": "Support", "assemblygroupdescription": "Axle"}]},
            ]}
    result = project(data, identity)
    assert result["counts"] == {
        "categories": 1, "subcategories": None, "part_types": 2, "positions": 2,
        "articles": 2, "oems": 1, "positions_with_oem": 1, "positions_without_oem": 1,
    }
    assert result["plan"]["payload"]["kind"] == "commercial"
    assert result["plan"]["payload"]["source_snapshot_sha"] == project(data, identity)["plan"]["payload"]["source_snapshot_sha"]
    assert result["plan"]["payload"]["categories"][0]["source_node_ids"] == [99, 101]
    assert result["plan"]["payload"]["categories"][1]["article_count"] == 0
