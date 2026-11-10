"""Versioned, read-only semantic review of the 113 supplied PRD proposals.

Not a publish request or vehicle-fitment approval. No database/network imports.
"""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.catalogue_carpot_sections import SECTIONS, SUBCATEGORIES

# Exact source IDs reviewed against full descriptions. Values reference existing
# corporate paths; None deliberately records a taxonomy gap rather than guessing.
INPUT_SHA256 = 'd2e9d9c50a58a177bcca587493b92b2599cf94b7e1d6b95760172a32abc2d5c8'
GROUPS = [
 (7,1,'1'), (7,0,'2 4 288'),
 (11,2,'7 8 9 424 3069 3224 3356 3357 6331'),
 (0,5,'27 42 44 138 3939 3945 3947 4272'),
 (11,0,'38 39 179'), (3,1,'51 914'),
 (0,3,'56 548 830 1260 2055 2394 3944'),
 (4,1,'78 1164 1165 2169 5213'), (4,0,'82 402 1419'),
 (4,2,'83'), (4,3,'412 2254'), (4,None,'387'),
 (8,None,'105 112 1092 3853'), (8,0,'106 107'), (8,1,'110 114 115'),
 (5,None,'127 219 1510 5025'),
 (0,0,'135 150 247 318 319 321 322 323 455 572 574 582 584 593 757 1217 1269 1270'),
 (2,2,'188 189 854 1180'), (3,0,'191'), (6,2,'215 3694'),
 (2,None,'251 273 1080 2462 3229 3406'),
 (5,4,'298 794 1191 1192 1194 1561'), (0,4,'305'),
 (9,0,'447 448 851'), (5,0,'450'), (5,1,'514'),
 (2,3,'654'), (2,4,'657 2070 3792 5171'), (0,2,'686'),
 (7,None,'807'), (5,3,'1914'), (7,2,'2232'),
 (0,None,'4175'), (9,2,'4394'), (9,3,'5750'),
]
# Name corrections remove unsupported placement/assembly/function assertions.
CORRECTIONS = {
 38:'Зчіпний пристрій причепа', 39:'Причіпне обладнання',
 572:'Сальник колінчастого вала', 914:'Наконечник поперечної кермової тяги',
 2232:'Датчик швидкості колеса / контролю тиску шин',
 3406:'Опора корпусу колісного підшипника',
 4175:'Датчик температури / тиску оливи',
 5213:'Штуцер прокачування гальмівного супорта',
 6331:'Очищення каталізатора',
}
AMBIGUITIES = {
 38:'Назва не визначає точний склад зчіпного пристрою.',
 2232:'Джерело змішує швидкість колеса й контроль тиску; потрібен опис артикула.',
 3406:'Не ототожнювати опору корпусу підшипника з поворотним кулаком.',
 4175:'Не визначено, чи це комбінований датчик, чи альтернативні функції.',
 5025:'Не визначено розташування аеродефлектора.',
 6331:'Назва може означати послугу або хімічний засіб; товарний тип не доведений.',
}
OPTIONAL = {38,39,127,179,215,1510,3792,5025,5171}
# Source labels describe kits or subparts, never confirmed physical memberships.
ASSEMBLIES = {2,4,78,387,447,1260,1561}
CONSUMABLE_KINDS = {'витратний матеріал','ущільнення','хімія','ремонтний комплект'}


DUPLICATE_REASONS = {
 657:'PRD 657 має usage «Колесо», 2070 — порожнє usage. Немає артикульного/розмірного доказу тотожності; залишити обидва ID.',
 2070:'Семантично схожий колісний болт 657, але usage порожнє; різьба, розміри й артикули не підтверджені.',
 830:'Група «Охлаждение»; інші однойменні датчики мають контексти кондиціонера, розжарювання та сумішоутворення. Не merge.',
 2055:'Група «Кондиционер» суперечить автоматичному зведенню до датчика системи охолодження двигуна; потрібен артикул.',
 2394:'Група «Система накаливания» не доводить застосовність до T6 бензин; не виключати за групою без артикульного fitment.',
 3944:'Група «Приготовление смеси»; однойменний датчик може мати іншу функцію/установку. Потрібні артикульні зв’язки.',
}
CONTEXT_PATH=Path(__file__).resolve().parents[1]/'docs/universal-catalogue/volvo-review/volvo-113-source-context.json'


def review(proposals, source_context=None):
    fingerprint=hashlib.sha256(json.dumps(proposals,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if fingerprint != INPUT_SHA256:
        raise ValueError('Source proposals changed; re-review required')
    by_id = {}
    for row in proposals:
        key = row['source_id']
        if not isinstance(key,int) or key in by_id:
            raise ValueError('Invalid/duplicate source ID')
        by_id[key] = row
    context_rows=json.loads(CONTEXT_PATH.read_text()) if source_context is None else source_context
    context={r['id']:r for r in context_rows}
    if len(context_rows)!=len(context) or context.keys()!=by_id.keys():
        raise ValueError('Source context identity mismatch')
    for key,row in context.items():
        sha=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if sha!=by_id[key]['source_sha256'] or row['description']!=by_id[key]['original_name']:
            raise ValueError('Source context checksum mismatch')
    paths = {}
    for section, subcategory, ids in GROUPS:
        for key in map(int,ids.split()):
            if key in paths:
                raise ValueError('Repeated curated ID')
            paths[key] = (SECTIONS[section], SUBCATEGORIES[section][subcategory][0] if subcategory is not None else None)
    if by_id.keys() != paths.keys():
        raise ValueError('Review must cover exactly the curated 113 IDs')
    duplicate_names = defaultdict(list)
    for key,row in by_id.items():
        duplicate_names[row['name_uk_proposal'].casefold()].append(key)
    result = []
    for key, old in sorted(by_id.items()):
        category, subcategory = paths[key]
        issues = []
        if not subcategory:
            issues.append('Чинний довідник не має однозначної підкатегорії без вигадування розташування/функції.')
        if key in AMBIGUITIES:
            issues.append(AMBIGUITIES[key])
        duplicate = [i for i in duplicate_names[old['name_uk_proposal'].casefold()] if i != key]
        if duplicate:
            issues.append(DUPLICATE_REASONS[key])
        kind = old['record_kind_proposal']
        record_type = ('needs_review' if key in AMBIGUITIES else
                       'equipment' if key in OPTIONAL else
                       'consumable' if kind in CONSUMABLE_KINDS else 'physical_part')
        applicability = 'NON_DISMANTLING' if record_type == 'consumable' else 'OPTIONAL' if key in OPTIONAL else 'UNKNOWN'
        result.append(dict(source_id=key,product_id=key,original_name=old['original_name'],
                           ukrainian_name=CORRECTIONS.get(key,old['name_uk_proposal']),
                           category=category,subcategory=subcategory,type=record_type,
                           role='assembly_candidate' if key in ASSEMBLIES else 'component_candidate' if kind=='компонент' else 'standalone_or_unresolved',
                           applicability=applicability, duplicate_candidate=duplicate,
                           evidence=f"PRD {key}: {old['original_name']}; SHA-256 {old['source_sha256']}. Semantic review v2; not VIN/placement evidence.",
                           source_context=context[key], duplicate_review='checked_keep_separate' if duplicate else 'not_flagged',
                           decision='needs_review' if issues else 'proposed', unresolved_reasons=issues,
                           canonical_candidate_ids=old['canonical_candidate_ids'], canonical_reuse='requires_context_review',
                           stock_link_status='UNVERIFIED_NO_DATABASE_READ',
                           prior_proposal=old, owner_approval='PENDING_OWNER_REVIEW'))
    return result


def summary(rows):
    return dict(source_rows=len(rows),category_proposals=len(rows),
                subcategory_proposals=sum(bool(r['subcategory']) for r in rows),
                unresolved_rows=sum(r['decision']=='needs_review' for r in rows),
                proposed_rows=sum(r['decision']=='proposed' for r in rows),
                duplicate_suspect_rows=sum(bool(r['duplicate_candidate']) for r in rows),
                duplicate_checked_rows=sum(r['duplicate_review']=='checked_keep_separate' for r in rows),
                non_dismantling_proposals=sum(r['applicability']=='NON_DISMANTLING' for r in rows),
                possible_existing_id_rows=sum(bool(r['canonical_candidate_ids']) for r in rows),
                applicability=dict(Counter(r['applicability'] for r in rows)),
                physical_placements_verified=0,vin_fitment_verified=0,stock_links='UNVERIFIED',
                database_writes=0,publish_ready=False)


def write(output, rows):
    output.mkdir(parents=True,exist_ok=True)
    (output/'volvo-113-reviewed.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    (output/'volvo-113-preview.json').write_text(json.dumps(summary(rows),ensure_ascii=False,indent=2)+'\n')
    fields=['source_id','product_id','original_name','ukrainian_name','category','subcategory','type','role','applicability','duplicate_candidate','evidence','decision','unresolved_reasons','canonical_candidate_ids','stock_link_status']
    with (output/'volvo-113-reviewed.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in row.items() if k in fields})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=review(json.loads(args.input.read_text()))
    write(args.output,rows)
    print(json.dumps(summary(rows),ensure_ascii=False,indent=2))
