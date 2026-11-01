# CarPot Catalogue Normalization v1.0 — Stage 1 audit register

Date: 2026-11-01
Scope: Warehouse PostgreSQL **staging only**. No SQL writes, category merges, rename operations, deployments, or production changes.
Status: **PARTIAL BASELINE — per-ID review pending authenticated export**.

## Baseline verified from R13 staging read-only audit

| Metric | Observed |
| --- | ---: |
| `categories` nodes | 3,855 |
| Exact-name duplicate groups (workspace + kind + parent ID + normalized name) | 590 |
| Member nodes in those groups | 2,957 |
| Duplicate groups with direct stock references | 590 |
| Physical `parts` records | 3,571 |
| Name-mapping rows | 15,444 |
| Current canonical types | 216 |
| `canonical_fitments` | 0 |

**Caution:** “stock references” counts links across `parts.category_id`, `parts.subcategory_id`, and `parts.checklist_category_id`, not individual physical pieces; the same stock row can count more than once. A duplicate name is not proof of identical semantics. R13 values are a historical snapshot, not live SQL counts for this document.

### Highest-exposure duplicate groups (sampling only)

| Name | Members | Direct stock links | Children | Sources | Disposition |
| --- | ---: | ---: | ---: | --- | --- |
| Силовий агрегат | 2 | 751 | 12 | carpot.base.v1 / carpot.v3 | review_required |
| Кузов | 2 | 549 | 29 | carpot.base.v1 / carpot.v3 | review_required |
| Ходова частина | 2 | 321 | 8 | carpot.base.v1 / carpot.v3 | review_required |
| Салон | 2 | 286 | 11 | carpot.base.v1 / carpot.v3 | review_required |
| Охолодження | 2 | 169 | 8 | carpot.base.v1 / carpot.v3 | review_required |
| Освітлення | 2 | 83 | 5 | carpot.base.v1 / carpot.v3 | review_required |
| Двері | 36 | 36 | 0 | carpot.v3 | review_required |
| Гальмівний супорт | 20 | 20 | 0 | carpot.v3 | review_required |
| Фара | 20 | 20 | 0 | carpot.v3 | review_required |

No merge action is authorized by this table.

## Name review — complete R13 status distribution

| Status | Rows |
| --- | ---: |
| unchanged | 6,211 |
| exact_name | 2,895 |
| language_review | 5,897 |
| unmapped | 321 |
| translation_proposal | 72 |
| review_hierarchy | 12 |
| review_context | 24 |
| dictionary | 12 |
| **Total** | **15,444** |

The curated proposal file includes **58 unique translation proposals** and **15 hierarchy proposals**, all marked pending; 72 `translation_proposal` is the number of source matching rows, not the number of dictionary proposals.

## Stage 1 data products required for completion

1. **Full duplicate register**: all 590 groups and 2,957 individual source IDs with original name, kind, workspace hash, parent ID, source, archive state, stock references, children, risk, review status. Existing endpoint: `/api/v1/catalogue/admin/audit/duplicate-review.csv`.
2. **Name mapping register**: all 15,444 mapping rows with original name, suggested name, source, level, mapping status, row count, and archive flag. Existing endpoint: `/api/v1/catalogue/admin/audit/catalogue-mapping.csv`.
3. **Proposal register**: curated 58+15 pending items from `warehouse/docs/catalogue-ua-proposals-r13.csv`.
4. **Dependency verification**: before any decision is implemented, inspect all FK and application references, not only the three `parts` category columns captured by R13.
5. **Fitment conflict inventory**: record proven model associations and unknown states separately. An empty `canonical_fitments` table does **not** prove universal compatibility or a clean fitment catalog.

## Review/decision schema (not yet applied)

`source_table | legacy_id | workspace_hash | kind | original_parent_id | original_name | source_system | stock_ref_count | child_count | proposed_category | proposed_subcategory | proposed_part_type | proposed_uk_name | candidate_canonical_id | decision (merge_mapping | keep_separate | rename | review_required) | rationale | evidence | approval | reviewer | reviewed_at`

Preserve existing identifiers and stock foreign keys until explicit approval, dry-run diff, rollback plan, and staging acceptance.

## Stage 1 acceptance status

| Check | State |
| --- | --- |
| Historical R13 summary preserved | CONFIRMED |
| 73 curated proposals available | CONFIRMED |
| Full 590 groups / 2,957 IDs exported and independently inspected | NOT VERIFIED |
| Full 15,444 mapping rows exported and independently inspected | NOT VERIFIED |
| Current staging SQL counts rechecked | NOT VERIFIED |
| All foreign-key dependencies inventoried | NOT VERIFIED |
| Cross-brand/model/generation conflicts audited | NOT VERIFIED |
| Data modifications | NONE |

**Next action**: obtain both existing owner-only exports through an authenticated session or a strictly read-only database connection, then review the full data by impact, language, hierarchy, and vehicle applicability. Do not mark Stage 1 complete until the missing checks are verified.

## Sources
- `warehouse/docs/catalogue-normalization-r13-staging-findings.md`
- `warehouse/docs/catalogue-ua-proposals-r13.csv`
- `warehouse/backend/app/catalogue_audit_once.py`
- R14 admin-only audit endpoints in `warehouse/backend/app/api/catalogue.py`
