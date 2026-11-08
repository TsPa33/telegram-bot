"""Explicit isolated staging schema preparation / read-only diagnostics.

No source database connection. No DDL unless --apply-additive-schema is passed.
"""
import argparse,os,json
from pathlib import Path
from selective_import import connection,check_space


def schema_statements(sql):
    sql='\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
    statements=[part.strip() for part in sql.split(';') if part.strip()]
    if any(not part.startswith('CREATE TABLE IF NOT EXISTS catalogue_') for part in statements):
        raise ValueError('Unexpected DDL')
    return statements


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--confirm-staging',action='store_true')
    p.add_argument('--apply-additive-schema',action='store_true')
    a=p.parse_args()
    if not a.confirm_staging or os.getenv('DEST_HOST') not in ('localhost','127.0.0.1') or os.getenv('DEST_DATABASE') not in ('railway','catalogue') or os.getenv('DEST_PORT')==os.getenv('SOURCE_PORT','3306'):
        p.error('Confirmed separate catalogue-staging tunnel required')
    with connection('DEST',os.environ['DEST_DATABASE']) as db:
        used=check_space(db)
        with db.cursor() as c:
            if a.apply_additive_schema:
                sql=Path(__file__).with_name('volvo_integration.sql').read_text('utf-8')
                for statement in schema_statements(sql):
                    c.execute(statement)
                db.commit()
            c.execute('SELECT COUNT(*) AS unique_volvo_oem_links FROM catalogue_oem WHERE oem_manufacturer_id=120')
            counts=c.fetchone()
            c.execute('SELECT car_id,model_id,coverage,sha256,observed_at FROM catalogue_volvo_snapshots ORDER BY car_id')
            counts['modifications']=c.fetchall()
        print(json.dumps(dict(estimated_database_mib=used,**counts),default=str))


if __name__=='__main__':main()
