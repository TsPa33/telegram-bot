"""Project one authenticated Oracle source graph onto the Warehouse plan contract."""

from datetime import datetime, timezone
from functools import lru_cache
import logging
from time import monotonic

from fastapi import HTTPException

from oracle_gateway import source_graph
from volvo_contract import digest, encode

logger = logging.getLogger("carpot.oracle_source_graph")
SOURCE_SCOPE = "oracle_vehicle_prd_article_oem"


def live_graph(identity):
    # Cache a complete observation for at most two minutes. Failed and empty
    # observations can be retried without waiting for cache expiration.
    return cached_graph(identity["kind"], identity["manufacturer_id"], identity["model_id"],
                        identity["car_id"], int(monotonic() // 120))


class NoGraph(Exception):
    def __init__(self, response):
        self.response = response


@lru_cache(maxsize=32)
def _available_graph(kind, manufacturer_id, model_id, car_id, window):
    identity = dict(kind=kind, manufacturer_id=manufacturer_id, model_id=model_id, car_id=car_id)
    data = source_graph(identity)
    try:
        if data["identity"] != identity:
            raise ValueError("identity")
        if data["status"] in ("absent", "identity_mismatch"):
            raise NoGraph(data)
        if data["status"] != "available":
            raise ValueError("status")
        return project(data, identity)
    except (TypeError, KeyError, ValueError, AttributeError, IndexError):
        logger.warning("oracle_source_graph_invalid_response kind=%s", kind)
        raise HTTPException(503, "Invalid Oracle source graph") from None


def cached_graph(kind, manufacturer_id, model_id, car_id, window):
    try:
        return _available_graph(kind, manufacturer_id, model_id, car_id, window)
    except NoGraph as result:
        return result.response


def project(data, identity):
    modification = data["modification"]
    if any(modification[field] != identity[field] for field in ("manufacturer_id", "model_id")):
        raise ValueError("modification identity")
    articles = data["articles"]
    links = {int(pid): ids for pid, ids in data["links"].items()}
    keys = set()
    oems = set()
    for sid, number, brand, codes in articles:
        if (type(sid) is not int or sid < 1 or not isinstance(number, str) or not number.strip()
                or len(number) > 150 or (brand is not None and not isinstance(brand, str))
                or not isinstance(codes, list)
                or any(not isinstance(code, str) or not code.strip() or len(code) > 150 for code in codes)
                or (sid, number) in keys):
            raise ValueError("article")
        keys.add((sid, number))
        oems.update(codes)

    positions = []
    used_articles = set()
    categories = set()
    products = set()
    positions_with_oem = 0
    for row in data["products"]:
        pid = row["product_id"]
        nodes = row["node_ids"]
        descriptions = row["descriptions"]
        article_ids = links.get(pid, [])
        if (type(pid) is not int or pid < 1 or pid in products
                or any(type(node) is not int or node < 0 for node in nodes)
                or len(set(article_ids)) != len(article_ids)
                or any(type(idx) is not int or not 0 <= idx < len(articles) for idx in article_ids)):
            raise ValueError("product")
        products.add(pid)
        used_articles.update(article_ids)
        label = descriptions[0] if len(descriptions) == 1 else {}
        name = label.get("description") or label.get("normalizeddescription")
        group = label.get("assemblygroupdescription")
        if group:
            categories.add(group)
        # PRD assembly group is a source label. PDS node IDs are retained
        # separately since a native category hierarchy has not been verified.
        position = dict(product_id=pid, kind="part" if name else "review", name_source=name or "",
                        category_path=[group] if group else [], article_count=len(article_ids),
                        source_node_ids=nodes, source_product_descriptions=descriptions,
                        source_fitment_linked=bool(article_ids))
        if label:
            position["source_prd_sha256"] = digest(label)
        positions.append(position)
        positions_with_oem += any(articles[idx][3] for idx in article_ids)
    if not positions or not links.keys() <= products or len(used_articles) != len(articles):
        raise ValueError("incomplete graph")

    sha = digest(data)
    article_graph = dict(items=articles, product_links={str(pid): ids for pid, ids in links.items()})
    plan = dict(schema="carpot.vehicle.plan.v1", **identity,
                modification={"description": modification["description"],
                              "constructioninterval": modification["construction_interval"]},
                observed_at=datetime.now(timezone.utc).isoformat(), source_snapshot_sha=sha,
                coverage="partial", coverage_verified=False, taxonomy_status="unreviewed",
                article_graph_sha=digest(article_graph), categories=positions)
    counts = dict(categories=len(categories), subcategories=None, part_types=len(products),
                  positions=len(positions), articles=len(keys), oems=len(oems),
                  positions_with_oem=positions_with_oem, positions_without_oem=len(positions) - positions_with_oem)
    result = dict(identity=identity, status="available", source_scope=SOURCE_SCOPE,
                  plan=dict(payload=plan, sha256=digest(plan)), counts=counts,
                  article_graph=article_graph)
    # The existing Warehouse read boundary is 8 MiB. Never return a silently
    # truncated plan as a complete observation.
    if len(encode(result)) > 8 * 1024 * 1024:
        raise ValueError("graph exceeds transport limit")
    return result
