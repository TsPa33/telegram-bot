"""Regression tests for Aleto catalogue discovery from manufacturer pages."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase


def load_application():
    path = Path(__file__).with_name('carpot_local_aleto.pyw')
    loader = SourceFileLoader('carpot_local_aleto_discovery_test', str(path))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class CatalogueDiscoveryTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_application()

    def test_polestar_2_2023_found_on_manufacturer_page(self):
        html = b'''<html>
          <a href="/ua/car/polestar-2-2021-/">Polestar 2 2021-2025</a>
          <a href="https://aleto.ua/ua/car/polestar-3-2024-/">Polestar 3</a>
          <a href="https://other.example/car/polestar-2-2021-/">Untrusted</a>
        </html>'''
        matches = self.app.find_brand_page_candidates(
            html, 'https://aleto.ua/ua/mark/polestar/', 'POLESTAR', 'Polestar 2', 2023)
        self.assertEqual(matches, ['https://aleto.ua/ua/car/polestar-2-2021-/'])
        self.assertEqual(
            self.app.find_brand_page_candidates(
                html, 'https://aleto.ua/ua/mark/polestar/', 'POLESTAR', 'Polestar 2', 2020), [])

    def test_untrusted_and_wrong_model_links_rejected(self):
        html = b'''<a href="https://other.example/car/polestar-2-2021-/">Fake</a>
                     <a href="/ua/car/polestar-3-2024-/">Other model</a>'''
        self.assertEqual(self.app.find_brand_page_candidates(
            html, 'https://aleto.ua/ua/mark/polestar/', 'Polestar', 'Polestar 2', 2023), [])

    def test_sitemap_filter_still_accepts_polestar(self):
        xml = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://aleto.ua/ua/car/polestar-2-2021-/</loc></url>
          <url><loc>https://aleto.ua/car/polestar-3-2024-/</loc></url>
        </urlset>'''
        self.assertEqual(self.app.find_candidates(xml, 'POLESTAR', 'Polestar 2', 2023),
                         ['https://aleto.ua/ua/car/polestar-2-2021-/'])
