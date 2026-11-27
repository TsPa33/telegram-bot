from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from catalogue_client import CatalogueClient, includes_year


class CatalogueClientTest(TestCase):
    def test_cascade_uses_parent_and_caches_only_directory(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalogue.sqlite3'
            client = CatalogueClient(path)
            row = {'id': 16, 'name': 'Модифікація', 'construction_interval': '04/2016–2021'}
            client._request = Mock(return_value={'items': [row], 'next_after': 16})
            rows, cursor, timestamp = client.page('modification', kind='passenger', parent=12)
            self.assertEqual((rows, cursor, timestamp), ([row], 16, None))
            client._request.assert_called_once_with(
                '/vehicles/vin/source-modifications', params={'model_id': 12, 'kind': 'passenger', 'after': 0},
            )
            reopened = CatalogueClient(path)
            rows, cursor, timestamp = reopened.page('modification', kind='passenger', parent=12, offline=True)
            self.assertEqual((rows, cursor), ([row], 16))
            self.assertIsNotNone(timestamp)
            self.assertFalse(reopened.connected)

    def test_vin_decode_requires_make_and_model(self):
        client = CatalogueClient()
        client._request = Mock(return_value={'vehicle': {'manufacturer': 'Audi', 'model': 'Q5'}})
        self.assertEqual(client.decode('12345678901234567')['model'], 'Q5')
        client._request.return_value = {'vehicle': {'manufacturer': 'Audi'}}
        with self.assertRaises(ValueError):
            client.decode('12345678901234567')

    def test_year_bounds_and_unknown_interval(self):
        for period, year, expected in (
            ('04/2016–2021', 2016, True), ('201612-', 2024, True),
            ('-2022', 2023, False), ('2016-2022', 2023, False), (None, 2022, False),
            (None, None, True), ('2018-2020', 2017, False),
        ):
            with self.subTest(period=period, year=year):
                self.assertEqual(includes_year(period, year), expected)
