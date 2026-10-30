"""Create fresh synthetic R8.3 DB only; refuse existing DB or remote host."""
import os,re
from pathlib import Path
from sqlalchemy.engine import make_url
u=make_url(os.environ['WAREHOUSE_TEST_DATABASE_URL'])
if u.host!='127.0.0.1' or not re.fullmatch(r'warehouse_r83(?:_[a-z0-9]+)*_test',u.database or ''):raise SystemExit('Dedicated loopback warehouse_r83_*_test only')
source=Path(__file__).with_name('seed-r81.py').resolve()
code=source.read_text().replace('warehouse_r81_test',u.database).replace('/tmp/r81-fixture.json','/tmp/r83-fixture.json').replace('r81-','r83-').replace('R8.1','R8.3')
exec(compile(code,str(source),'exec'),{'__file__':str(source),'__name__':'__main__'})
