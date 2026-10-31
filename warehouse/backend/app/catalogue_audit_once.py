"""One-shot staging catalogue audit. Strictly SELECT in PostgreSQL READ ONLY transaction.

No identity/PII, stock prices, VIN, user notes, OEM, or session values are logged.
Do not import from the production runtime or any background worker.
"""
import hashlib
import json
import logging
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.config import database_url

LOG = logging.getLogger("warehouse.catalogue.audit")
TAG = "CAT_AUDIT_20261101"
DATA = Path(__file__).resolve().parent / "data"

RUSSIAN = re.compile(r"[ыъёэЫЪЁЭ]|\b(?:передний|передняя|задний|задняя|левый|правая|правый|левая|двигатель|дверь|двери|крыло|крылья|подвеска|рулевое|тормозной|стекло|крыша|коробка|оборудование|отделка|безопасность|внутренняя|сборе|запчасти|топливная|колеса|жидкости|брызговик|предохранителей|электрика|трансмиссия|освещение)\b", re.I)
CANONICAL_CATEGORY_CANDIDATES = {
    "Двигун": "Силовий агрегат",
    "Двері": "Кузов / Двері",
    "Інтер’єр / салон": "Салон",
    "Підвіска та кермове управління": "Ходова частина",
    "Трансмісія": "Силовий агрегат / Трансмісія",
    "Колеса": "Ходова частина / Колеса",
    "Оливи та рідини": "Витратні матеріали (окремий перегляд)",
    "Тормозная система": "Гальмівна система",
    "Подвеска и рулевое": "Ходова частина",
    "Двигатель": "Силовий агрегат",
    "Салон": "Салон",
}
def norm(s):
    return " ".join(re.sub(r"[^\w]+", " ", str(s or "").casefold()).split())

def account_tag(raw):
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:10]

def audited():
    if os.getenv("WAREHOUSE_ENV") != "staging":
        raise RuntimeError("Read-only audit is staging-only")
    manifest = json.loads((DATA / "aleto_subcategories_uk.json").read_text(encoding="utf-8"))
    rules = json.loads((DATA / "canonical_rules_v1_5.json").read_text(encoding="utf-8"))
    universal = json.loads((DATA / "canonical_universal_v2c.json").read_text(encoding="utf-8"))
    canonical_names = {norm(v["name"]): v["name"] for v in universal["types"]}
    # A source alias alone is never proof of category, placement, OEM, or fitment.
    aliases = defaultdict(set)
    for rule in rules["types"]:
        for alias in rule.get("aliases", []):
            aliases[norm(alias)].add(rule["name"])
    counts = {}
    errors = []
    mapping = []
    group_counts = Counter()
    type_counts = Counter()
    stats = {}
    engine = create_engine(database_url(), poolclass=NullPool, connect_args={"connect_timeout":5})
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout='25000ms'")
            def query(label,sql):
                try:
                    with connection.begin_nested():  # SAVEPOINT: recover one bad read without aborting all reads.
                        rows=[dict(r) for r in connection.execute(text(sql)).mappings().all()]
                    counts[label]=len(rows)
                    return rows
                except Exception as exc:
                    errors.append({"query":label,"type":type(exc).__name__})
                    LOG.warning("%s_QUERY_ERROR %s %s",TAG,label,type(exc).__name__)
                    return []
            db_counts=query("totals","""SELECT 'categories' k, count(*) n FROM categories UNION ALL
              SELECT 'dismantling_catalog_types', count(*) FROM dismantling_catalog_types UNION ALL
              SELECT 'parts',count(*) FROM parts UNION ALL
              SELECT 'canonical_types',count(*) FROM canonical_types UNION ALL
              SELECT 'canonical_mappings',count(*) FROM canonical_mappings UNION ALL
              SELECT 'catalogue_entities',count(*) FROM catalogue_entities UNION ALL
              SELECT 'catalogue_aliases',count(*) FROM catalogue_aliases UNION ALL
              SELECT 'aleto_taxonomy',count(*) FROM aleto_taxonomy UNION ALL
              SELECT 'aleto_applications',count(*) FROM aleto_applications UNION ALL
              SELECT 'vehicle_checklist_items',count(*) FROM vehicle_checklist_items UNION ALL
              SELECT 'canonical_fitments',count(*) FROM canonical_fitments UNION ALL
              SELECT 'vehicles',count(*) FROM vehicles""")
            stats["table_counts"]={r["k"]:r["n"] for r in db_counts}
            rows = query("categories","""SELECT c.id,c.account_id,c.source,c.kind,c.name,c.parent_id,p.name parent_name,c.archived
              FROM categories c LEFT JOIN categories p ON p.id=c.parent_id ORDER BY c.account_id,c.kind,c.parent_id,c.name,c.id""")
            for r in rows:
                mapping.append(dict(s="categories",i=r["id"],w=account_tag(r["account_id"]),k=r["kind"],p=r["parent_name"] or "",
                                   o=r["name"],u=0,src=r["source"],a=bool(r["archived"])))
            parts=query("parts_distinct","""SELECT p.account_id,p.name,p.category_id,p.subcategory_id,
                   count(*) n, sum(CASE WHEN p.archived THEN 0 ELSE 1 END) active,
                   min(c.name) category_name,min(sc.name) subcategory_name
                FROM parts p LEFT JOIN categories c ON c.id=p.category_id
                LEFT JOIN categories sc ON sc.id=p.subcategory_id
                GROUP BY p.account_id,p.name,p.category_id,p.subcategory_id
                ORDER BY p.account_id,p.name""")
            for r in parts:
                mapping.append(dict(s="parts",i="",w=account_tag(r["account_id"]),k="part",p=" / ".join(filter(None,[r["category_name"],r["subcategory_name"]])),
                                  o=r["name"],u=r["n"],src="stock",a=False))
            rows=query("dismantling_types","""SELECT account_id,category_name,subcategory_name,name,position,count(*) n,
                     count(DISTINCT source_id) sources
               FROM dismantling_catalog_types GROUP BY account_id,category_name,subcategory_name,name,position
               ORDER BY account_id,category_name,subcategory_name,name,position""")
            for r in rows:
                mapping.append(dict(s="dismantling_types",i="",w=account_tag(r["account_id"]),k="part",p=r["category_name"]+" / "+r["subcategory_name"],
                                    o=r["name"],u=r["n"],src="legacy-import",a=False))
            rows=query("aleto_raw_taxonomy","""SELECT account_id,raw_category,raw_subcategory,normalization_status,
                       count(*) n FROM aleto_taxonomy GROUP BY account_id,raw_category,raw_subcategory,normalization_status
                       ORDER BY account_id,raw_category,raw_subcategory,normalization_status""")
            for r in rows:
                mapping.append(dict(s="aleto_taxonomy",i="",w=account_tag(r["account_id"]),k="subcategory",p=r["raw_category"],
                                    o=r["raw_subcategory"],u=r["n"],src=r["normalization_status"],a=False))
            rows=query("global_entities","""SELECT id,kind,name,parent_id,normalized_name
                 FROM catalogue_entities WHERE kind IN ('category','subcategory','part_type')
                 ORDER BY kind,parent_id,name""")
            lookup={r["id"]:r["name"] for r in rows}
            for r in rows:
                mapping.append(dict(s="catalogue_entities",i=r["id"],w="GLOBAL",k=r["kind"],p=lookup.get(r["parent_id"],""),
                                    o=r["name"],u=0,src="global-v2",a=False))
            rows=query("canonical_types","""SELECT id,name,category,subcategory FROM canonical_types ORDER BY category,subcategory,name""")
            for r in rows:
                mapping.append(dict(s="canonical_types",i=r["id"],w="GLOBAL",k="part_type",p=r["category"]+" / "+r["subcategory"],
                                    o=r["name"],u=0,src="canonical-v3",a=False))
            rows=query("checklist_types","""SELECT account_id,name_en,name_uk,source,pt_id,count(*) n
                  FROM vehicle_checklist_items GROUP BY account_id,name_en,name_uk,source,pt_id
                  ORDER BY name_en,pt_id""")
            for r in rows:
                mapping.append(dict(s="checklists",i=str(r["pt_id"]),w=account_tag(r["account_id"]),k="part_type",p="",
                                    o=r["name_uk"] or r["name_en"],u=r["n"],src=r["source"],a=False))
            mappings=query("published_mapping_status","""SELECT quality,count(*) n FROM canonical_mappings m
                 INNER JOIN canonical_state s ON s.snapshot_sha=m.snapshot_sha
                 GROUP BY quality""")
            stats["published_quality"]={r["quality"]:r["n"] for r in mappings}
            sources=query("supplier_models","""SELECT manufacturer,model,count(*) AS offers
                  FROM aleto_models m JOIN aleto_applications a ON a.model_id=m.id AND a.account_id=m.account_id
                  GROUP BY manufacturer,model ORDER BY manufacturer,model""")
            stats["aleto_model_links"]=sources
            fit=query("fitment_status","""SELECT status,count(*) n FROM canonical_fitments GROUP BY status""")
            stats["fitment_records"]={r["status"]:r["n"] for r in fit}
            checks=query("category_integrity","""SELECT
                 count(*) FILTER (WHERE c.parent_id IS NOT NULL AND p.id IS NULL) AS broken_parents,
                 count(*) FILTER (WHERE c.parent_id=c.id) AS self_parents,
                 count(*) FILTER (WHERE c.parent_id IS NOT NULL AND c.account_id<>p.account_id) AS cross_workspace_parents
                 FROM categories c LEFT JOIN categories p ON p.id=c.parent_id""")
            stats["category_integrity"]=checks[0] if checks else {}
            dup_parts=query("possible_stock_duplicates","""SELECT count(*) n,sum(cnt) affected
                FROM (SELECT vehicle_id,category_id,subcategory_id,
                         lower(regexp_replace(trim(name),'\\s+',' ','g')) part_name,
                         NULLIF(trim(oem_number),'') oem,count(*) cnt
                      FROM parts WHERE NOT archived AND vehicle_id IS NOT NULL
                      GROUP BY vehicle_id,category_id,subcategory_id,lower(regexp_replace(trim(name),'\\s+',' ','g')),NULLIF(trim(oem_number),'')
                      HAVING count(*)>1) d""")
            stats["stock_same_donor_name_groups"]=dup_parts[0] if dup_parts else {}
            # Derived suggestions are NEVER applied to source tables.
            seen=defaultdict(list)
            for row in mapping:
                source=row["o"]
                kind=row["k"]
                target=manifest.get(source) if kind=="subcategory" else None
                reason=""
                status="unchanged"
                if source=="Комп":
                    target=None;status="manual_review";reason="Unresolved source abbreviation"
                elif target and norm(target)!=norm(source):
                    status="dictionary";reason="Explicit Aleto dictionary"
                elif kind=="category" and source in CANONICAL_CATEGORY_CANDIDATES:
                    target=CANONICAL_CATEGORY_CANDIDATES[source]
                    status="review_hierarchy";reason="Category tree differs between providers"
                elif norm(source) in canonical_names and kind in ("part","part_type"):
                    target=canonical_names[norm(source)]
                    status="exact_name";reason="Exact canonical name; fitment and context unverified"
                elif kind in ("part","part_type") and len(aliases[norm(source)])==1:
                    target=next(iter(aliases[norm(source)]))
                    status="review_context";reason="Unique name alias; placement, category and equipment still unverified"
                elif RUSSIAN.search(source):
                    status="language_review";reason="Likely Russian-language text"
                elif kind=="subcategory" and target is None:
                    status="unmapped";reason="No verified subcategory dictionary mapping"
                if status=="unchanged":
                    target=source
                row.update(n=target or "",t=status)
                group_counts[status]+=1
                type_counts[row["s"]]+=1
                if row["s"]=="categories":
                    seen[(row["w"],row["k"],norm(row["p"]),norm(row["n"]))].append(row)
            duplicate_groups=[{
               "workspace":k[0],"kind":k[1],"parent":values[0]["p"],"target":values[0]["n"],
               "count":len(values),"source_names":sorted(set(v["o"] for v in values)),
               "ids":[v["i"] for v in values]
            } for k,values in seen.items() if len(values)>1]
            stats["same_parent_category_duplicate_groups"]=duplicate_groups[:250]
            stats["same_parent_category_duplicate_total"]=len(duplicate_groups)
            stats["name_mapping_status"]=dict(group_counts)
            stats["rows_by_source"]=dict(type_counts)
            stats["mapping_total"]=len(mapping)
            stats["errors"]=errors
            connection.rollback()
    finally:
        engine.dispose()

    # Railway drops bursts >500 log lines/s. The authenticated download endpoint
    # delivers the *complete* dataset; startup prints only safe aggregates.
    short={k:v for k,v in stats.items() if k!="same_parent_category_duplicate_groups"}
    LOG.warning("%s_SUMMARY %s",TAG,json.dumps(short,ensure_ascii=False,separators=(",",":"),default=str))
    for i,group in enumerate(stats["same_parent_category_duplicate_groups"][:12]):
        LOG.warning("%s_DUP %d %s",TAG,i,json.dumps(group,ensure_ascii=False,separators=(",",":"),default=str))
    examples=[r for r in mapping if r["t"] in ("dictionary","review_hierarchy","manual_review","language_review","review_context")]
    for i in range(0,min(len(examples),60),10):
        LOG.warning("%s_SAMPLE %d %s",TAG,i//10,json.dumps(examples[i:i+10],ensure_ascii=False,separators=(",",":"),default=str))
    LOG.warning("%s_END mapping=%d review=%d errors=%d",TAG,len(mapping),len(examples),len(errors))
    return stats,mapping

def run():
    try:
        audited()
    except Exception:
        LOG.exception("%s_FAILED Read-only audit could not complete",TAG)
