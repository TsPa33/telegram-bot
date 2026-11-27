"""Inspect live catalogue candidates and optionally parse a selected listing page."""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json

from app.services.aleto_adapter import MAX_PAGE_BYTES, extract_page
from app.services.aleto_discovery import MAX_SITEMAP_BYTES, catalogue_candidates
from app.services.aleto_source import AletoSource

SITEMAPS = (
    'https://aleto.ua/sitemap-categories.xml',
    'https://aleto.ua/sitemap-categories-new.xml',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manufacturer')
    parser.add_argument('model')
    parser.add_argument('--year', type=int)
    parser.add_argument('--generation', default='')
    parser.add_argument('--catalogue', help='Full URL of the selected candidate')
    args = parser.parse_args()

    client = AletoSource()
    try:
        candidates = {}
        for sitemap in SITEMAPS:
            xml = client.read(sitemap, max_bytes=MAX_SITEMAP_BYTES, allowed_types=('text/xml', 'application/xml'))
            for item in catalogue_candidates(
                xml, args.manufacturer, args.model, year=args.year, generation=args.generation,
            ):
                candidates[item.url] = asdict(item)
        if not candidates:
            print(json.dumps({'status': 'SOURCE_NOT_FOUND'}))
            return
        if not args.catalogue:
            status = 'NEEDS_CLARIFICATION' if len(candidates) > 1 else 'CANDIDATE_FOUND'
            print(json.dumps({'status': status, 'candidates': list(candidates.values())}))
            return
        if args.catalogue not in candidates:
            parser.error('the selected catalogue is absent from the candidates')
        html = client.read(args.catalogue, max_bytes=MAX_PAGE_BYTES, allowed_types=('text/html',))
        page = extract_page(
            html.decode('utf-8-sig'), args.catalogue, datetime.now(UTC).isoformat(),
            manufacturer=args.manufacturer, model=args.model, source='aleto',
            data_origin='public_html_probe', adapter_version='catalogue-probe-v1',
        )
        offers = {row['source_article']: row for row in page['rows']}
        print(json.dumps({
            'status': 'COMPLETE_WITH_ERRORS' if page['issues'] else 'COMPLETE',
            'cards': page['cards'],
            'unique_offers': len(offers),
            'offers_with_oem': sum(bool(row['oem']) for row in offers.values()),
            'offers_with_price': sum(
                row['price_uah'] is not None or row['price_usd'] is not None for row in offers.values()
            ),
            'errors': len(page['issues']),
            'discovered_links': len(page['links']),
        }))
    except (ValueError, OSError) as exc:
        code = str(exc)
        parser.exit(1, (code if code.isascii() and code.replace('_', '').isalnum() else 'SOURCE_PROBE_FAILED') + '\n')


if __name__ == '__main__':
    main()
