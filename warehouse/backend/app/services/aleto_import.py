"""Validated, additive Aleto reference import; the caller owns commit/rollback."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import gzip
import os
import tempfile
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import Account, Category
from app.models.aleto import AletoModel, AletoOffer, AletoPrice, AletoApplication, AletoTaxonomy

DICTIONARY = json.loads((Path(__file__).resolve().parents[1] / 'data/aleto_subcategories_uk.json').read_text())
BUNDLED_DIR = Path(__file__).resolve().parents[1] / 'data/aleto/v1'
BUNDLED_PACKAGE = BUNDLED_DIR / 'catalogue.sqlite3.gz'
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MODELS = {'Volvo XC40', 'Volvo XC60', 'Volvo XC90'}
CATEGORY_ALIASES = {
    'Інтер': 'Інтер’єр / салон', 'Интерьер / салон': 'Інтер’єр / салон', 'Салон': 'Інтер’єр / салон',
    'Двигатель': 'Двигун', 'Двери': 'Двері', 'Электрика': 'Електрика',
    'Тормозная система': 'Гальмівна система', 'Подвеска и рулевое': 'Підвіска та кермове управління',
    'Підвіска і рульове': 'Підвіска та кермове управління', 'Трансмиссия': 'Трансмісія',
    'Колёса': 'Колеса', 'Олія та рідини': 'Оливи та рідини', 'Масло и жидкости': 'Оливи та рідини',
}
CATEGORIES = {'Інтер’єр / салон', 'Двигун', 'Кузов', 'Двері', 'Електрика', 'Гальмівна система',
              'Підвіска та кермове управління', 'Трансмісія', 'Колеса', 'Оливи та рідини'}


def identity(value):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFC', value).replace("'", '’').split()).casefold()


def money(value):
    if value is None or value == '':
        return None
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or result >= Decimal('1000000000000') or result != result.quantize(Decimal('.01')):
            raise ValueError('Invalid source price')
        return result
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid source price') from None


def observation(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Source timestamp requires timezone')
    return result.astimezone(timezone.utc)


def source_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname not in {'aleto.ua', 'www.aleto.ua'} or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Invalid Aleto source URL')
    return value


def load_package(path):
    """SQLite is opened read-only; reject corrupt, partial or inconsistent exports."""
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError('Expected staging SQLite file, at most 64 MiB')
    if path.suffix == '.gz':
        with gzip.open(path, 'rb') as compressed:
            raw = compressed.read(MAX_PACKAGE_BYTES + 1)
        if len(raw) > MAX_PACKAGE_BYTES:
            raise ValueError('Decompressed package exceeds 64 MiB')
        with tempfile.TemporaryDirectory(prefix='warehouse-aleto-') as directory:
            unpacked = Path(directory) / 'catalogue.sqlite3'
            unpacked.write_bytes(raw)
            data = load_package(unpacked)
        if path == BUNDLED_PACKAGE.resolve():
            manifest = json.loads((BUNDLED_DIR / 'manifest.json').read_text())
            actual = {'offers': len(data['offers']), 'applications': len(data['applications']), 'taxonomy_paths': len(data['paths'])}
            if (data['sha256'] != manifest['sha256'] or actual != manifest['counts']
                    or hashlib.sha256(path.read_bytes()).hexdigest() != manifest['compressed_sha256']):
                raise ValueError('Bundled catalogue checksum or counts mismatch')
        return data
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Invalid staging database integrity')
        offers = [dict(r) for r in conn.execute('SELECT article,title,oem,condition,price_uah,price_usd,url,checked_at,price_status FROM offers ORDER BY article')]
        applications = [tuple(r) for r in conn.execute('SELECT model,article FROM applications ORDER BY model,article')]
        paths = [dict(r) for r in conn.execute('SELECT model,article,category,subcategory,raw_category,raw_subcategory FROM taxonomy_paths ORDER BY model,article,category,subcategory,raw_category,raw_subcategory')]
    if not offers or len(offers) > 100000 or len(paths) > 200000:
        raise ValueError('Empty or oversized staging dataset')
    articles = set()
    for row in offers:
        if not isinstance(row['article'], str) or not row['article'].strip() or len(row['article']) > 150 or row['article'] in articles:
            raise ValueError('Invalid or duplicate source article')
        if not row['title'] or not row['title'].strip():
            raise ValueError('Missing offer title')
        articles.add(row['article'])
        row['price_uah'], row['price_usd'] = money(row['price_uah']), money(row['price_usd'])
        row['observed_at'] = observation(row['checked_at'])
        source_url(row['url'])
        if row['price_status'] != ('missing' if row['price_uah'] is None else 'observed'):
            raise ValueError('Source price status disagrees with price')
    apps = set(applications)
    if len(apps) != len(applications) or {m for m, _ in apps} != MODELS or {a for _, a in apps} != articles:
        raise ValueError('Missing/duplicate model links or unexpected models')
    for model, article in apps:
        if model not in MODELS or article not in articles:
            raise ValueError('Invalid model link')
    path_keys = set()
    for row in paths:
        key = tuple(row.values())
        if key in path_keys:
            raise ValueError('Duplicate source taxonomy path')
        path_keys.add(key)
        if (row['model'], row['article']) not in apps or row['category'] not in CATEGORIES:
            raise ValueError('Invalid taxonomy relationship')
        if CATEGORY_ALIASES.get(row['raw_category'], row['raw_category']) != row['category'] or row['subcategory'] != row['raw_subcategory']:
            raise ValueError('Unverified source taxonomy transformation')
        if not row['raw_subcategory'] or any(len(row[k]) > 200 for k in ('raw_category', 'raw_subcategory')):
            raise ValueError('Invalid taxonomy label')
    if {(r['model'], r['article']) for r in paths} != apps:
        raise ValueError('Missing taxonomy for model link')
    return {'offers': offers, 'applications': applications, 'paths': paths,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def import_package(db: Session, account_id: str, data):
    """No commits, deletes, stock records, vehicle writes or audit history writes.

    Both dry-run and apply execute this same plan in an outer transaction.
    Lock the owner even in dry-run so concurrent catalogue imports serialize.
    """
    owner = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if owner is None or owner.role != 'DIRECTOR' or not owner.is_active:
        raise ValueError('Select an active Warehouse DIRECTOR workspace account')
    counts = {name: Counter() for name in ('models', 'categories', 'offers', 'prices', 'applications', 'taxonomy')}
    def bump(name, action):
        counts[name][action] += 1
    models = {r.manufacturer + ' ' + r.model: r for r in db.scalars(select(AletoModel).where(AletoModel.account_id == account_id))}
    for label in sorted(MODELS):
        if label not in models:
            models[label] = AletoModel(account_id=account_id, manufacturer='Volvo', model=label.split()[1])
            db.add(models[label]); bump('models', 'inserted')
        else:
            bump('models', 'skipped')
    db.flush()
    # Exact, parent-aware semantic matching preserves all existing IDs/names.
    categories = {}
    for row in db.scalars(select(Category).where(Category.account_id == account_id)):
        label = CATEGORY_ALIASES.get(row.name, row.name) if row.kind == 'category' else DICTIONARY.get(row.name, row.name)
        label = label or row.name
        key = (row.kind, row.parent_id, identity(label))
        categories.setdefault(key, []).append(row)
    resolved = {}
    def category(name, kind, parent_id=None):
        key = (kind, parent_id, identity(name))
        if key in resolved:
            return resolved[key]
        found = categories.get(key, [])
        if len(found) > 1 or (found and found[0].archived):
            raise ValueError(f'Ambiguous or archived category: {name}; resolve manually')
        if found:
            row = found[0]; bump('categories', 'skipped')
        else:
            digest = hashlib.sha256(repr(key).encode()).hexdigest()
            row = Category(account_id=account_id, source='aleto.v1', external_key=digest,
                           kind=kind, name=name, parent_id=parent_id)
            db.add(row); db.flush(); bump('categories', 'inserted')
            categories[key] = [row]
        resolved[key] = row
        return row
    offers = {r.source_article: r for r in db.scalars(select(AletoOffer).where(AletoOffer.account_id == account_id))}
    prices = {(r.offer_id, r.observed_at): r for r in db.scalars(select(AletoPrice).where(AletoPrice.account_id == account_id))}
    for item in data['offers']:
        values = dict(title=item['title'], oem=item['oem'] or None, condition=item['condition'],
                      source_url=item['url'], observed_at=item['observed_at'])
        row = offers.get(item['article'])
        if row is None:
            row = AletoOffer(account_id=account_id, source='aleto', source_article=item['article'], **values)
            db.add(row); db.flush(); offers[item['article']] = row; bump('offers', 'inserted')
        elif row.observed_at < item['observed_at']:
            for key, value in values.items():
                setattr(row, key, value)
            bump('offers', 'updated')
        elif row.observed_at == item['observed_at'] and any(getattr(row, k) != v for k, v in values.items()):
            raise ValueError(f'Conflicting offer at same timestamp: {item["article"]}')
        else:
            bump('offers', 'skipped')
        price = prices.get((row.id, item['observed_at']))
        price_values = dict(price_uah=item['price_uah'], price_usd=item['price_usd'], source_url=item['url'])
        if price is not None:
            if any(getattr(price, k) != v for k, v in price_values.items()):
                raise ValueError(f'Conflicting price at same timestamp: {item["article"]}')
            bump('prices', 'skipped')
        else:
            price = AletoPrice(account_id=account_id, offer_id=row.id, observed_at=item['observed_at'], **price_values)
            db.add(price); prices[(row.id, item['observed_at'])] = price; bump('prices', 'inserted')
    db.flush()
    applications = set(db.execute(select(AletoApplication.model_id, AletoApplication.offer_id).where(AletoApplication.account_id == account_id)))
    for model, article in data['applications']:
        key = (models[model].id, offers[article].id)
        if key not in applications:
            db.add(AletoApplication(account_id=account_id, model_id=key[0], offer_id=key[1])); applications.add(key)
            bump('applications', 'inserted')
        else:
            bump('applications', 'skipped')
    db.flush()
    paths = {(r.model_id, r.offer_id, r.raw_category, r.raw_subcategory): r for r in db.scalars(select(AletoTaxonomy).where(AletoTaxonomy.account_id == account_id))}
    pending = Counter()
    for item in data['paths']:
        root = category(item['category'], 'category')
        uk = DICTIONARY.get(item['raw_subcategory'])
        sub = category(uk, 'subcategory', root.id) if uk else None
        if uk is None:
            pending[item['raw_subcategory']] += 1
        key = (models[item['model']].id, offers[item['article']].id, item['raw_category'], item['raw_subcategory'])
        values = dict(category_id=root.id, subcategory_id=sub.id if sub else None, normalization_status='verified' if sub else 'pending')
        row = paths.get(key)
        if row is None:
            row = AletoTaxonomy(account_id=account_id, model_id=key[0], offer_id=key[1],
                               raw_category=key[2], raw_subcategory=key[3], **values)
            db.add(row); paths[key] = row; bump('taxonomy', 'inserted')
        elif any(getattr(row, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(row, k, v)
            bump('taxonomy', 'updated')
        else:
            bump('taxonomy', 'skipped')
    db.flush()
    return {'sha256': data['sha256'], 'counts': {name: {key: value[key] for key in ('inserted', 'updated', 'skipped')} for name, value in counts.items()},
            'input': {'offers': len(data['offers']), 'applications': len(data['applications']), 'taxonomy': len(data['paths'])},
            'models': dict(Counter(m for m, _ in data['applications'])),
            'pending_subcategories': dict(pending), 'missing_uah_prices': sum(r['price_uah'] is None for r in data['offers']),
            'missing_oem': sum(not r['oem'] for r in data['offers']), 'year_compatibility': 'unverified'}


def validate_target(url, environment, staging=False, railway_environment=None):
    name = make_url(url).database or ''
    if environment == 'production':
        raise ValueError('Production catalogue imports are prohibited')
    if staging:
        if (environment != 'staging' or name not in {'warehouse_staging', 'carpot_warehouse_staging'}
                or railway_environment not in (None, '', 'warehouse-staging')):
            raise ValueError('--staging requires WAREHOUSE_ENV=staging, warehouse_staging or carpot_warehouse_staging DB, and Railway environment warehouse-staging if present')
    elif not name.endswith('_test') or not name.startswith(('warehouse', 'carpot_warehouse')):
        raise ValueError('Only a dedicated Warehouse database ending in _test is permitted without --staging')


def main():
    parser = argparse.ArgumentParser(description='Aleto Catalogue v1; test or explicit staging, default dry-run')
    parser.add_argument('package', type=Path, nargs='?', default=BUNDLED_PACKAGE, help='SQLite or .sqlite3.gz; defaults to bundled, checksum-verified v1')
    parser.add_argument('--account-id', required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--apply', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--staging', action='store_true', help='Explicitly select the isolated warehouse-staging target; does not imply --apply')
    args = parser.parse_args()
    from app.config import database_url
    from app.db import engine
    # Explicit staging preparation; never use main DATABASE_URL or allow production.
    try:
        validate_target(database_url(), os.getenv('WAREHOUSE_ENV', ''), args.staging, os.getenv('RAILWAY_ENVIRONMENT_NAME'))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        data = load_package(args.package)
        with Session(engine()) as db:
            report = import_package(db, args.account_id, data)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        report.update(mode='apply' if args.apply else 'dry-run', committed=args.apply)
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.write_text(payload + '\n')
        print(payload)
    except (ValueError, sqlite3.Error, OSError, EOFError) as exc:
        parser.exit(1, f'Import rejected: {exc}\n')


if __name__ == '__main__':
    main()
