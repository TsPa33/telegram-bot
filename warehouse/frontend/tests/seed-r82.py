"""Fresh, guarded, EMPTY loopback runner fixture; refuses existing targets."""
import os,re
from pathlib import Path
from sqlalchemy.engine import make_url
u=make_url(os.environ['WAREHOUSE_TEST_DATABASE_URL'])
if u.host!='127.0.0.1' or not re.fullmatch(r'warehouse_r82(?:_[a-z0-9]+)*_test',u.database or ''):raise SystemExit('Dedicated loopback warehouse_r82_*_test required')
source=Path(__file__).with_name('seed-r81.py').resolve()
code=source.read_text().replace('warehouse_r81_test',u.database).replace('/tmp/r81-fixture.json','/tmp/r82-fixture.json').replace('r81-','r82-').replace('R8.1','R8.2')
exec(compile(code,str(source),'exec'),{'__file__':str(source),'__name__':'__main__'})
