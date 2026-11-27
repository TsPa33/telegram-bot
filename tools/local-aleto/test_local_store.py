from contextlib import closing
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import local_store

loader = SourceFileLoader('aleto_test_app', str(Path(__file__).with_name('carpot_local_aleto.pyw')))
app = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(app)
RECORD = {'source_article': 'A1', 'part_name': 'Фара', 'oem': 'КОД', 'price_uah': '100.00',
          'price_usd': '', 'category': 'Кузов', 'subcategory': 'Оптика', 'condition': '',
          'source_url': 'https://aleto.ua/part/a1/', 'source_page': 'https://aleto.ua/car/acura-mdx-2021-2023/',
          'observed_at': '2026-11-27T12:00:00+00:00'}


def build_v1(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
        CREATE TABLE jobs(id INTEGER PRIMARY KEY,manufacturer TEXT,model TEXT,year INTEGER,generation TEXT,
                          catalogue TEXT,status TEXT,error TEXT,created_at TEXT);
        CREATE TABLE pages(job_id INTEGER,url TEXT,status TEXT,errors INTEGER,PRIMARY KEY(job_id,url));
        CREATE TABLE parts(job_id INTEGER,page TEXT,article TEXT,payload TEXT,PRIMARY KEY(job_id,page,article));
        INSERT INTO jobs VALUES (1,'Acura','MDX',2022,'','https://aleto.ua/car/acura-mdx-2021-2023/',
                                 'completed','','2026-11-27T12:00:00+00:00');
        """)
        db.execute('INSERT INTO parts VALUES (1,?,?,?)',
                   (RECORD['source_page'], RECORD['source_article'], json.dumps(RECORD)))


class StoreTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        app.DATA_DIR = Path(directory.name)
        app.DB_PATH = app.DATA_DIR / 'local_aleto.sqlite3'

    def test_migrate_backup_and_history(self):
        build_v1(app.DB_PATH)
        with closing(app.connect_db()) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 11)
            self.assertEqual(db.execute('SELECT count(*) FROM parts').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT price FROM price_history').fetchone()[0], '100.00')
        backups = list(app.DATA_DIR.glob('local_aleto-before-v11-*.sqlite3'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(backup.execute('SELECT count(*) FROM parts').fetchone()[0], 1)

    def test_repeat_import_search_history_and_csv(self):
        source = app.DATA_DIR / 'independent.sqlite3'
        build_v1(source)
        before = source.read_bytes()
        with closing(app.connect_db()) as db:
            self.assertEqual(local_store.import_v1(db, source), 1)
            self.assertEqual(local_store.import_v1(db, source), 0)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(local_store.search(db, 1, 'код', 'КУЗОВ', True, True, True)), 1)
            self.assertEqual(len(local_store.search(db, 1, 'unmatched')), 0)
            self.assertEqual(len(local_store.search(db, 1, offset=100)), 0)
            with db:
                local_store.record_prices(db, 1, {**RECORD, 'price_uah': '110.00',
                                                   'observed_at': '2026-11-28T12:00:00+00:00'})
                local_store.add_vehicle(db, 'Acura', 'MDX', 2022, '', vin='12345678901234567')
        with closing(app.connect_db()) as reopened:
            self.assertEqual(reopened.execute('SELECT count(*) FROM price_history').fetchone()[0], 2)
            self.assertEqual(reopened.execute('SELECT model FROM vehicles').fetchone()[0], 'MDX')
        files, valid, invalid = app.export_csv(1, app.DATA_DIR / 'export')
        self.assertEqual((len(files), valid, invalid), (1, 1, 0))
        self.assertIn('A1,Acura,MDX', files[0].read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
