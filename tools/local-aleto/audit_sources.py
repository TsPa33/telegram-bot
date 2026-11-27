"""Inventory Aleto source copies without updating the input files (Python 3.12)."""
import argparse
from contextlib import closing
import csv
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def audit_sqlite(path):
    # SQLite may need to recover a WAL or create a shared-memory sidecar.
    # Allow that only in a temporary directory containing the supplied copies.
    with TemporaryDirectory(prefix='carpot-source-audit-') as directory:
        copy = Path(directory) / 'source.sqlite3'
        shutil.copyfile(path, copy)
        for suffix in ('-wal', '-journal'):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, copy.with_name(copy.name + suffix))
        with closing(sqlite3.connect(copy)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA query_only=ON')
            tables = db.execute("""SELECT name FROM pragma_table_list
                                  WHERE schema='main' AND type='table'
                                  AND name NOT LIKE 'sqlite_%' ORDER BY name""").fetchall()
            return [
                {'table': name, 'columns': [
                    {'name': field, 'type': declaration}
                    for field, declaration in db.execute(
                        'SELECT name, type FROM pragma_table_xinfo(?)', (name,),
                    )
                ], 'rows': db.execute(f'SELECT count(*) FROM {quote_identifier(name)}').fetchone()[0]}
                for name, in tables
            ]


def audit_csv(path, encoding, delimiter):
    with path.open(encoding=encoding, newline='') as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        header = next(reader, [])
        rows = mismatched = 0
        for row in reader:
            if row:
                rows += 1
                mismatched += len(row) != len(header)
    return {'columns': header, 'rows': rows, 'width_mismatches': mismatched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('copies', nargs='+', type=Path)
    parser.add_argument('--encoding', default='utf-8-sig')
    parser.add_argument('--delimiter', default=',', choices=[',', ';', '\t'])
    args = parser.parse_args()
    result = []
    for path in args.copies:
        item = {'file': path.name}
        try:
            item['bytes'] = path.stat().st_size
            item['inventory'] = (audit_csv(path, args.encoding, args.delimiter)
                                 if path.suffix.lower() == '.csv' else audit_sqlite(path))
        except (OSError, sqlite3.Error, UnicodeError, csv.Error) as error:
            item['error'] = str(error)
        result.append(item)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(any('error' in item for item in result))


if __name__ == '__main__':
    raise SystemExit(main())
