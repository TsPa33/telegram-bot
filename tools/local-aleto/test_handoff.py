from contextlib import closing
from pathlib import Path
from sqlite3 import connect
from tempfile import TemporaryDirectory
from unittest import TestCase

from local_store import install_seed
from migrate_handoff import import_legacy, migrate, readonly
from test_local_store import build_v1


class HandoffTest(TestCase):
    def test_merge_and_repeat_preserve_sources(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'local_aleto.sqlite3'
            build_v1(original)
            path = root / 'aleto.sqlite3'
            with closing(connect(path)) as db, db:
                db.executescript("""
                CREATE TABLE products(article TEXT,title TEXT,oem TEXT,condition TEXT,url TEXT,
                                      price_uah REAL,price_usd REAL,checked_at TEXT);
                CREATE TABLE product_models(article TEXT,model TEXT,category TEXT,subcategory TEXT,source_page TEXT);
                CREATE TABLE price_history(id INTEGER,article TEXT,old_uah REAL,new_uah REAL,
                                           old_usd REAL,new_usd REAL,changed_at TEXT);
                CREATE TABLE crawled_pages(url TEXT,model TEXT,checked_at TEXT,products_found INTEGER,error TEXT);
                INSERT INTO products VALUES ('A2','Фара','OEM','','https://aleto.ua/part/a2/',100,NULL,'2026-01-02T00:00:00+00:00');
                INSERT INTO product_models VALUES ('A2','Volvo XC90','Кузов','Оптика','https://aleto.ua/ua/car/volvo-xc90-16-/');
                INSERT INTO price_history VALUES (1,'A2',90,100,NULL,NULL,'2026-01-02T00:00:00+00:00');
                INSERT INTO crawled_pages VALUES ('https://aleto.ua/ua/car/volvo-xc90-16-/','Volvo XC90','2026-01-02T00:00:00+00:00',1,'');
                """)
            csv = root / 'parts.csv'
            csv.write_text('model,category,subcategory,article,oem,title,condition,price_uah,price_usd,url,checked_at,source_page\n'
                           'Volvo XC90,Кузов,Оптика,A2,OEM,Фара,,100.0,,https://aleto.ua/part/a2/,2026-01-02T00:00:00+00:00,https://aleto.ua/ua/car/volvo-xc90-16-/\n',
                           encoding='utf-8-sig')
            before = [p.read_bytes() for p in (original, path, csv)]
            output = root / 'migrated.sqlite3'
            result = migrate(root, output)
            with self.assertRaises(FileExistsError):
                migrate(root, output)
            with closing(readonly(path)) as legacy, closing(connect(output)) as db:
                self.assertEqual(import_legacy(db, legacy, csv), result)
                self.assertEqual(db.execute('SELECT count(*) FROM parts').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT count(*) FROM jobs WHERE vehicle_id IS NOT NULL').fetchone()[0], 0)
                self.assertEqual(db.execute('SELECT old_uah FROM legacy_price_changes').fetchone()[0], 90)
            self.assertEqual([p.read_bytes() for p in (original, path, csv)], before)
            installed = root / 'first-run' / 'local_aleto.sqlite3'
            install_seed(output, installed)
            self.assertEqual(installed.read_bytes(), output.read_bytes())
            installed.write_bytes(b'existing')
            install_seed(output, installed)
            self.assertEqual(installed.read_bytes(), b'existing')
