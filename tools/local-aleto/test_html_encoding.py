"""Prevent isolated non-UTF-8 Aleto pages from terminating a catalogue crawl."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import TestCase


def load_app():
    p = Path(__file__).with_name('carpot_local_aleto.pyw')
    loader = SourceFileLoader('carpot_html_encoding_test', str(p))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class AletoHtmlEncodingTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_app()

    def test_utf8_html_preserves_cyrillic(self):
        raw = '<html><body>Фара Volvo XC90</body></html>'.encode('utf-8')
        text, warning_count = self.app.decode_html_page(raw)
        self.assertIn('Фара', text)
        self.assertEqual(warning_count, 0)

    def test_explicit_windows1251_charset(self):
        raw = ('<html><head><meta charset="windows-1251"></head>'
               '<body>Фара задня права</body></html>').encode('cp1251')
        text, warning_count = self.app.decode_html_page(raw)
        self.assertIn('Фара задня права', text)
        self.assertEqual(warning_count, 0)

    def test_one_bad_byte_does_not_lose_remaining_html(self):
        raw = (b'<html><body>' +
               'Фара Volvo'.encode('utf-8') +
               b'\xd1' +
               'Двері задні'.encode('utf-8') +
               b'<a href="/ua/car/volvo-xc90-16-/page-2/">Next</a></body></html>')
        text, warnings = self.app.decode_html_page(raw)
        self.assertEqual(warnings, 1)
        self.assertIn('Фара Volvo', text)
        self.assertIn('Двері задні', text)
        self.assertIn('page-2', text)

    def test_invalid_utf8_in_part_name_does_not_produce_corrupt_export(self):
        part = ('<div class="detail-item"><div class="detail-item-title">'
                '<a href="/part/abc">Фара\uFFFD</a></div>'
                '<div class="detail-item-chars"><small>Арт: <b>123456</b></small>'
                '</div></div>')
        rows, links, errors, cards = self.app.extract_page(
            part, 'https://aleto.ua/car/volvo-xc90-16-/')
        self.assertEqual((rows, errors, cards), ([], 1, 1))

    def test_too_many_invalid_bytes_fail_explicitly(self):
        raw = b'<html><body>' + b'\xff' * 120 + b'</body></html>'
        with self.assertRaises(self.app.SourceError):
            self.app.decode_html_page(raw)

    def test_unknown_meta_charset_fails_without_guessing(self):
        with self.assertRaises(self.app.SourceError):
            self.app.decode_html_page(b'<html><meta charset="x-unknown"></html>')
