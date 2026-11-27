"""Regression: Aleto multi-page links must be crawled across /car and /ua/car."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase


def app_module():
    path = Path(__file__).with_name('carpot_local_aleto.pyw')
    loader = SourceFileLoader('aleto_pagination_app', str(path))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class CataloguePaginationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app_module()
        cls.root = 'https://aleto.ua/car/polestar-2-2021-/'

    def test_same_model_ua_pagination_accepted(self):
        self.assertTrue(self.app.within_catalogue(
            'https://aleto.ua/ua/car/polestar-2-2021-/page-2/', self.root))
        self.assertTrue(self.app.within_catalogue(
            'https://aleto.ua/car/polestar-2-2021-/page-11/', self.root))
        self.assertTrue(self.app.within_catalogue(
            'https://aleto.ua/ua/car/polestar-2-2021-/sistema-ohlajdeniya/', self.root))
        self.assertFalse(self.app.within_catalogue(
            'https://aleto.ua/car/polestar-3-2024-/page-2/', self.root))
        self.assertFalse(self.app.within_catalogue(
            'https://attacker.example/car/polestar-2-2021-/page-2/', self.root))

    def test_independent_link_extraction_yields_pages_and_categories(self):
        html = """<html><div><a class="detail-cat-item"
          href="/ua/car/polestar-2-2021-/sistema-ohlajdeniya/">Cooling</a>
          <a href="/ua/car/polestar-2-2021-/page-2/">2</a>
          <a rel="next" href="/car/polestar-2-2021-/page-3/">Next</a>
          <a href="/car/polestar-3-2024-/page-2/">other</a>
          </div></html>"""
        records, links, errors, cards = self.app.extract_page(html, self.root)
        self.assertEqual(cards, 0)
        self.assertEqual(records, [])
        self.assertEqual(errors, 0)
        self.assertEqual(links, [
            'https://aleto.ua/ua/car/polestar-2-2021-/sistema-ohlajdeniya/',
            'https://aleto.ua/ua/car/polestar-2-2021-/page-2/',
            'https://aleto.ua/car/polestar-2-2021-/page-3/',
        ])

    def test_ua_root_crawls_ru_page(self):
        self.assertTrue(self.app.within_catalogue(
            self.root + 'page-2/', 'https://aleto.ua/ua/car/polestar-2-2021-/'))
