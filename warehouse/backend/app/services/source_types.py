"""Exact pt_id identities, conservative decisions and explicit category-only repair."""

import hashlib, json, re
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from fastapi import HTTPException
from app.models import Category, SourceTypeMapping, Part, VehicleChecklistItem, now
from app.services.inventory import snapshot, record
from app.services.plan_parts_classification import (
    classify,
    match_existing_category,
    normalize,
    CATEGORY_ALIASES,
)
from app.services.catalogue_carpot_sections import SECTIONS, SUBCATEGORIES

MARKER = re.compile(r"^plan\.parts:ktype=(\d+);pt_id=(\d+)$")


class Resolver:
    def __init__(self, db, account_id, *, provision=False):
        self.db, self.account_id = db, account_id
        all_categories = list(
            db.scalars(select(Category).where(Category.account_id == account_id))
        )
        self.categories = [c for c in all_categories if not c.archived]
        archived_keys = {
            (c.source, c.external_key) for c in all_categories if c.archived
        }
        self.mappings = {
            m.pt_id: m
            for m in db.scalars(
                select(SourceTypeMapping).where(
                    SourceTypeMapping.account_id == account_id,
                    SourceTypeMapping.source == "plan.parts",
                )
            )
        }
        self.new_nodes = []
        if provision:
            for i, section in enumerate(SECTIONS):
                aliases = {normalize(x) for x in CATEGORY_ALIASES[section]} | {
                    normalize(section)
                }
                roots = [
                    c
                    for c in self.categories
                    if c.kind == "category"
                    and c.parent_id is None
                    and normalize(c.name) in aliases
                ]
                if (
                    not roots
                    and ("carpot.corporate", "root:" + str(i)) not in archived_keys
                ):
                    root = Category(
                        id=str(
                            uuid5(
                                NAMESPACE_URL,
                                account_id + ":carpot:category:" + section,
                            )
                        ),
                        account_id=account_id,
                        name=section,
                        kind="category",
                        parent_id=None,
                        archived=False,
                        source="carpot.corporate",
                        external_key="root:" + str(i),
                    )
                    self.categories.append(root)
                    self.new_nodes.append(root)
                    roots = [root]
                if len(roots) == 1:
                    root = roots[0]
                    for name, _ in SUBCATEGORIES[i]:
                        children = [
                            c
                            for c in self.categories
                            if c.parent_id == root.id
                            and c.kind == "subcategory"
                            and normalize(c.name) == normalize(name)
                        ]
                        if not children:
                            child = Category(
                                id=str(uuid5(NAMESPACE_URL, root.id + ":" + name)),
                                account_id=account_id,
                                name=name,
                                kind="subcategory",
                                parent_id=root.id,
                                archived=False,
                                source="carpot.corporate",
                                external_key="sub:" + str(i) + ":" + name,
                            )
                            self.categories.append(child)
                            self.new_nodes.append(child)

    def resolve(self, pt_id, original, translated=""):
        old = self.mappings.get(pt_id)
        valid = {c.id: c for c in self.categories}
        if old and normalize(old.source_name) != normalize(original):
            return {
                "kind": "review",
                "section": None,
                "category_id": None,
                "subcategory_id": None,
                "mapping": "review_required",
                "reason": "supplier_type_changed",
                "type_key": old.type_key,
            }
        if old and normalize(old.source_name) == normalize(original):
            root = valid.get(old.category_id)
            sub = valid.get(old.subcategory_id)
            if (
                root
                and root.parent_id is None
                and root.kind == "category"
                and (
                    not old.subcategory_id
                    or sub
                    and sub.parent_id == root.id
                    and sub.kind == "subcategory"
                )
            ):
                return {
                    **old.decision,
                    "category_id": root.id,
                    "subcategory_id": sub.id if sub else None,
                    "type_key": old.type_key,
                }
        decision = match_existing_category(
            self.db,
            self.account_id,
            classify(original),
            translated or original,
            categories=self.categories,
        )
        return {**decision, "type_key": f"carpot:plan-parts:{pt_id}"}

    def persist(self, pt_id, original, decision):
        old = self.mappings.get(pt_id)
        payload = {
            k: v
            for k, v in decision.items()
            if k not in ("category_id", "subcategory_id", "type_key")
        }
        if old and normalize(old.source_name) != normalize(original):
            return  # Changed vendor meaning requires review, never overwrite history.
        if (
            old
            and old.category_id == decision.get("category_id")
            and old.subcategory_id == decision.get("subcategory_id")
            and old.decision == payload
        ):
            return
        previous = (
            {k: v for k, v in snapshot(old).items() if k != "history"} if old else None
        )
        if old is None:
            old = SourceTypeMapping(
                account_id=self.account_id,
                source="plan.parts",
                pt_id=pt_id,
                type_key=decision["type_key"],
                source_name=original,
                decision=payload,
                history=[],
            )
            self.db.add(old)
            self.mappings[pt_id] = old
        old.category_id = decision.get("category_id")
        old.subcategory_id = decision.get("subcategory_id")
        old.decision = payload
        old.history = [
            *old.history,
            {"at": now().isoformat(), "before": previous, "after": decision},
        ]


def normalization(db, who, v, *, apply=False, token=None, provision=False):
    resolver = Resolver(db, who.workspace_account_id, provision=provision)
    parts = list(
        db.scalars(
            select(Part)
            .where(Part.account_id == who.workspace_account_id, Part.vehicle_id == v.id)
            .order_by(Part.id)
            .with_for_update()
            if apply
            else select(Part)
            .where(Part.account_id == who.workspace_account_id, Part.vehicle_id == v.id)
            .order_by(Part.id)
        )
    )
    source = {
        (r.ktype, r.pt_id): r
        for r in db.scalars(
            select(VehicleChecklistItem).where(
                VehicleChecklistItem.account_id == who.workspace_account_id,
                VehicleChecklistItem.vehicle_id == v.id,
            )
        )
    }
    decisions = []
    for p in parts:
        marker = MARKER.fullmatch(p.compatibility_notes or "")
        row = source.get((int(marker[1]), int(marker[2]))) if marker else None
        if not row and marker and int(marker[2]) in resolver.mappings:
            from types import SimpleNamespace

            known = resolver.mappings[int(marker[2])]
            row = SimpleNamespace(
                pt_id=known.pt_id,
                name_en=known.source_name,
                name_uk=p.name,
                ktype=int(marker[1]),
            )
            source[(row.ktype, row.pt_id)] = row
        d = (
            resolver.resolve(row.pt_id, row.name_en, row.name_uk or p.name)
            if row
            else {}
        )
        # Every existing non-null assignment is protected; never guess manual provenance.
        status = (
            "protected"
            if p.category_id or p.subcategory_id
            else "matched" if d.get("category_id") else "review"
        )
        decisions.append(
            {
                "part_id": p.id,
                "pt_id": row.pt_id if row else None,
                "name": p.name,
                "old": {
                    "category_id": p.category_id,
                    "subcategory_id": p.subcategory_id,
                },
                "proposed": d,
                "status": status,
            }
        )
    body = {
        "vehicle_id": v.id,
        "provision": provision,
        "decisions": decisions,
        "nodes": [
            {"id": c.id, "name": c.name, "parent_id": c.parent_id}
            for c in resolver.new_nodes
        ],
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if apply:
        if token != digest:
            raise HTTPException(
                409, "Категорії змінилися. Повторіть перевірку перед застосуванням."
            )
        db.add_all(resolver.new_nodes)
        db.flush()
        for node in resolver.new_nodes:
            record(db,who.workspace_account_id,node,'category_create','Явне налаштування корпоративного довідника',{},flush_before=False)
        byid = {p.id: p for p in parts}
        for d in decisions:
            if d["status"] != "matched":
                continue
            p = byid[d["part_id"]]
            before = snapshot(p)
            p.category_id = d["proposed"]["category_id"]
            p.subcategory_id = d["proposed"]["subcategory_id"]
            row = source[(int(MARKER.fullmatch(p.compatibility_notes)[1]), d["pt_id"])]
            resolver.persist(d["pt_id"], row.name_en, d["proposed"])
            record(
                db,
                who.workspace_account_id,
                p,
                "part_update",
                "Однозначна корпоративна категоризація; залишок і ціна не змінюються",
                before,
            )
        db.commit()
    return {
        **body,
        "token": digest,
        "applied": apply,
        "updated_count": (
            sum(d["status"] == "matched" for d in decisions) if apply else 0
        ),
        "can_apply": sum(d["status"] == "matched" for d in decisions),
        "needs_review": sum(d["status"] == "review" for d in decisions),
        "rows": [
            {
                "part_id": d["part_id"],
                "section": d["proposed"].get("section"),
                "action": d["status"],
            }
            for d in decisions
        ],
        "counts": {
            s: sum(d["status"] == s for d in decisions)
            for s in ("matched", "review", "protected")
        },
    }
