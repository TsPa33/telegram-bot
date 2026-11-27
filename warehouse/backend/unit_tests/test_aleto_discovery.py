import pytest

from app.services.aleto_adapter import extract_page, fixture, run_fixture
from app.services.aleto_discovery import catalogue_candidates


def sitemap(*paths):
    entries = ''.join(
        f'<url><loc>{url}</loc></url>'
        for url in paths
    )
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'.encode()


def test_explicit_candidates_filter_year_generation_and_disallowed_urls():
    old = 'https://aleto.ua/car/bmw-x4-f26-2014-2018/'
    new = 'https://aleto.ua/ua/car/bmw-x4-g02-2019-2023/'
    xml = sitemap(
        old, new, new.replace('/ua/', '/'), new + 'kuzov/',
        new.replace('aleto.ua', 'other.example'), new.replace('bmw-x4-', 'bmw-x40-'),
    )
    assert [item.url for item in catalogue_candidates(xml, 'BMW', 'X4')] == [old, new]
    assert [item.url for item in catalogue_candidates(xml, 'BMW', 'X4', year=2018)] == [old]
    assert [item.url for item in catalogue_candidates(xml, 'BMW', 'X4', generation='G02')] == [new]
    assert catalogue_candidates(xml, 'BMW', 'X4', year=1990) == []
    assert catalogue_candidates(xml, 'Unknown', 'X4') == []


def test_legacy_year_ranges_and_open_end():
    xml = sitemap(
        'https://aleto.ua/car/toyota-camry-v55-15-17/',
        'https://aleto.ua/car/toyota-camry-v70-18-/',
    )
    [candidate] = catalogue_candidates(xml, 'Toyota', 'Camry', year=2020)
    assert (candidate.year_from, candidate.year_to) == (2018, None)


@pytest.mark.parametrize('xml', [
    b'<?xml version="1.0"?><!DOCTYPE urlset [<!ENTITY e "test">]><urlset/>',
    b'<html>Access denied</html>',
    b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url>',
])
def test_rejects_invalid_or_unexpected_source_documents(xml):
    with pytest.raises(ValueError, match='INVALID_SITEMAP'):
        catalogue_candidates(xml, 'BMW', 'X4')


@pytest.mark.parametrize('model', ['XC40', 'XC60', 'XC90'])
def test_existing_fixture_provenance_and_output_are_preserved(model):
    summary, _ = run_fixture(model, fixture(model)[1], lambda *args: None)
    assert summary['exportable_offers'] == 2
    assert summary['error_count'] == 0
    assert summary['data_source'] == 'synthetic_offline_fixture'


def test_extractor_accepts_model_outside_fixture_set():
    manifest, _ = fixture('XC60')
    page = manifest['pages'][0]
    result = extract_page(
        page['html'], page['url'], page['observed_at'],
        manufacturer='Acura', model='MDX', source='test-sample',
        data_origin='test', adapter_version='test',
    )
    [row] = result['rows']
    assert (row['manufacturer'], row['model'], row['source']) == ('Acura', 'MDX', 'test-sample')
    assert not result['issues']


def test_source_checks_robots_and_never_requests_disallowed_path(monkeypatch):
    from app.services.aleto_source import AletoSource, SourceUnavailable

    source = AletoSource()
    paths = []

    def request(host, path, max_bytes, allowed_types):
        paths.append(path)
        if path == '/robots.txt':
            return b'User-agent: *\nDisallow: /car/private/\n'
        return b'public'

    monkeypatch.setattr(source, '_request', request)
    with pytest.raises(SourceUnavailable, match='ROBOTS_DISALLOWED'):
        source.read('https://aleto.ua/car/private/', max_bytes=100, allowed_types=('text/html',))
    with pytest.raises(ValueError, match='INVALID_SOURCE_URL'):
        source.read('https://aleto.ua.example/car/public/', max_bytes=100, allowed_types=('text/html',))
    assert paths == ['/robots.txt']
    assert source.read(
        'https://aleto.ua/car/public/', max_bytes=100, allowed_types=('text/html',),
    ) == b'public'
    assert paths == ['/robots.txt', '/car/public/']


def test_source_rejects_nonpublic_dns_before_socket_creation(monkeypatch):
    import socket

    from app.services.aleto_source import PublicHTTPSConnection, SourceUnavailable

    monkeypatch.setattr(
        socket, 'getaddrinfo',
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))],
    )
    with pytest.raises(SourceUnavailable, match='SOURCE_ADDRESS_REJECTED'):
        PublicHTTPSConnection('aleto.ua').connect()


def test_source_refuses_redirects(monkeypatch):
    from app.services import aleto_source

    class Redirect:
        status = 302

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, method, target, **kwargs):
            assert method == 'GET'
            assert target == '/robots.txt'

        def getresponse(self):
            return Redirect()

        def close(self):
            pass

    monkeypatch.setattr(aleto_source, 'PublicHTTPSConnection', Connection)
    with pytest.raises(aleto_source.SourceUnavailable, match='SOURCE_HTTP_302'):
        aleto_source.AletoSource().read('https://aleto.ua/car/a/', max_bytes=100, allowed_types=('text/html',))
