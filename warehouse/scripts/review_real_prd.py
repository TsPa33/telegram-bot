"""Offline proposal audit. No DB, HTTP, approval or publication operations."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.canonical_rules import TYPES, norm
from app.services.catalogue_carpot_sections import propose_section, propose_subcategory, SECTIONS
from inspect_resume_inputs import verify
from app.services.universal_catalogue import prepare, prd_record


def csv_member(path, suffix):
    with zipfile.ZipFile(path) as z:
        matches = [i for i in z.infolist() if i.filename.endswith(suffix)]
        if len(matches) != 1 or matches[0].file_size > 40 * 1024 * 1024:
            raise ValueError('Missing, duplicate or oversized CSV: ' + suffix)
        return list(csv.DictReader(io.StringIO(z.read(matches[0]).decode('utf-8-sig'))))


def indexed(rows, key):
    result = {}
    for row in rows:
        value = int(row[key])
        if value <= 0 or value in result:
            raise ValueError('Duplicate/invalid source ID')
        result[value] = row
    return result


def recheck(row):
    """An exclusion is a proposal, never a deletion. Chemical groups are mixed."""
    decision = row['screening_decision']
    if decision not in {'EXCLUDE', 'REVIEW', 'KEEP_CANDIDATE'}:
        raise ValueError('Unknown screening decision')
    if decision == 'EXCLUDE' and 'химическ' in row['source_group'].casefold():
        return 'REVIEW', 'mixed_chemical_group_requires_item_review'
    return decision, 'inherited_proposal_not_approved'


def audit(directory):
    directory = Path(directory)
    raw = csv_member(directory / 'carpot_prd_export_result.zip', 'carpot_prd_all_raw.csv')
    screened = csv_member(directory / 'carpot_prd_safe_filter_v1.zip', 'carpot_prd_screening_all_26938.csv')
    source = indexed(raw, 'id')
    screening = indexed(screened, 'source_id')
    if source.keys() != screening.keys():
        raise ValueError('Raw/screening identity mismatch')
    fields = [('assemblygroupdescription', 'source_group'), ('description', 'source_full_name'),
              ('normalizeddescription', 'source_generic_name'), ('usagedescription', 'source_usage')]
    for key, row in source.items():
        if any(row[a].strip() != screening[key][b].strip() for a, b in fields):
            raise ValueError(f'Raw/screening context mismatch: {key}')
    for suffix, expected in [('carpot_prd_excluded_3833.csv', 'EXCLUDE'), ('carpot_prd_remaining_23105.csv', None)]:
        subset = indexed(csv_member(directory / 'carpot_prd_safe_filter_v1.zip', suffix), 'source_id')
        required = {k for k, r in screening.items() if (r['screening_decision'] == 'EXCLUDE') == (expected == 'EXCLUDE')}
        if subset.keys() != required or any(subset[k] != screening[k] for k in subset):
            raise ValueError('Screening partition mismatch')
    pilot_path = directory / 'CarPot_taxonomy_pilot_2026_11_10.zip'
    pilot = csv_member(pilot_path, '01_xc90_113_category_review.csv')
    pilots = indexed(pilot, 'source_product_id')
    names = defaultdict(list)
    for key, value in TYPES.items():
        names[norm(value['name'])].append(key)
    proposals = []
    for key, row in source.items():
        previous = screening[key]
        p = pilots.get(key, {})
        decision, reason = recheck(previous)
        title = p.get('name_uk_review_proposal') or previous['part_name_uk_proposal']
        section = propose_section(previous['source_group'], '', title or row['description'])['section']
        # Pilot section is an explicit review proposal, not a new taxonomy.
        if p.get('carpot_section') in SECTIONS:
            section = p['carpot_section']
        sub = propose_subcategory(section, previous['source_group'], '', title or row['description'])
        candidates = list(names.get(norm(title), []))  # Name candidates only; legacy paths need explicit review.
        proposals.append(dict(source_id=key, source_sha256=prd_record({**row, 'id': key})['source_sha'],
                              original_name=row['description'], name_uk_proposal=title, section=section,
                              subcategory=sub['subcategory'], record_kind_proposal=p.get('catalogue_record_kind') or previous['record_class'],
                              screening_decision=decision, reason=reason, canonical_candidate_ids=candidates,
                              approval='PENDING_OWNER_REVIEW', fitment='UNKNOWN', canonical_context_verified=False,
                              volvo_default_proposal=p.get('dismantling_default')))
    collisions = defaultdict(list)
    for p in proposals:
        if p['source_id'] in pilots:
            collisions[norm(p['name_uk_proposal'])].append(p['source_id'])
    # Reference IDs must be checked against full source descriptions; no fuzzy merging.
    trial = csv_member(pilot_path, '03_xc90_421_review_candidates_NOT_INVENTORY.csv')
    references = []
    for row in trial:
        pointer = row['catalogue_prd_id'].strip()
        if pointer:
            found = source.get(int(pointer)) if pointer.isdigit() else None
            references.append(dict(candidate_id=row['candidate_id'], proposed_name=row['name_uk'], source_id=pointer,
                                   actual_name=found['description'] if found else None, status='REQUIRES_SEMANTIC_REVIEW' if found else 'INVALID_POINTER'))
    expansion = csv_member(pilot_path, '02_xc90_193_expansion_review.csv')
    full_names = defaultdict(list)
    for key, row in source.items():
        full_names[norm(row['description'])].append(key)
    expansion_review = [dict(name=r['source_name'], exact_full_name_source_ids=full_names.get(norm(r['source_name']), []), approval='PENDING_OWNER_REVIEW') for r in expansion]
    table = []
    for section in [*SECTIONS, None]:
        rows = [r for r in proposals if r['source_id'] in pilots and r['section'] == section]
        table.append(dict(category=section or 'Потребує категоризації', source_types=len(rows),
                          candidate_types=sum(r['volvo_default_proposal'] != 'не включати' for r in rows),
                          non_dismantling=sum(r['volvo_default_proposal'] == 'не включати' for r in rows),
                          confirmed_physical_positions=0, unknown_fitment_types=len(rows), incompatible_verified=0))
    preview_counts = [prepare([{**r, 'id': int(r['id'])} for r in raw[n:n+500]])['counts'] for n in range(0,len(raw),500)]
    summary = dict(publication_preview_batches=preview_counts, raw_rows=len(raw), unique_source_ids=len(source), pilot_rows=len(pilot),
                   screening_before=dict(Counter(r['screening_decision'] for r in screened)),
                   screening_after=dict(Counter(r['screening_decision'] for r in proposals)),
                   exclusion_reopened=sum(r['reason'] == 'mixed_chemical_group_requires_item_review' for r in proposals),
                   ukrainian_name_proposals=sum(bool(r['name_uk_proposal']) for r in proposals),
                   corporate_section_proposals=sum(bool(r['section']) for r in proposals),
                   corporate_subcategory_proposals=sum(bool(r['subcategory']) for r in proposals),
                   existing_canonical_candidates=sum(bool(r['canonical_candidate_ids']) for r in proposals),
                   pilot_defaults=dict(Counter(r['dismantling_default'] for r in pilot)),
                   pilot_kinds=dict(Counter(r['catalogue_record_kind'] for r in pilot)),
                   same_name_not_automerge={k:v for k,v in collisions.items() if len(v)>1},
                   expansion_rows=len(expansion), expansion_exact_matches=sum(bool(r['exact_full_name_source_ids']) for r in expansion_review),
                   trial_reference_count=len(references), invalid_trial_pointers=sum(r['status']=='INVALID_POINTER' for r in references),
                   categories=table, coverage='partial_unverified', verified_physical_positions=0,
                   target_500_proven=False, publication=dict(approved_rows=0, writes=0, blocked='Owner review, source fitment and placement evidence required'))
    return summary, proposals, references, expansion_review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if a.output.resolve().is_relative_to(repo) or a.output.exists():
        p.error('Use a new output directory outside the repository')
    verified = verify(a.archive)
    summary, proposals, references, expansion = audit(verified['directory'])
    summary['archive_sha256'] = hashlib.sha256(a.archive.read_bytes()).hexdigest()
    summary['verified_packages'] = verified['verified']
    a.output.mkdir(parents=True)
    for name, data in [('summary',summary), ('row-proposals',proposals), ('trial-references',references), ('expansion-review',expansion)]:
        (a.output / (name+'.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
