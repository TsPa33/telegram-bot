"""Fresh R1 fixture reuses the guarded UI-3 synthetic catalogue seeder, never real data."""
from pathlib import Path
import json
source=Path(__file__).with_name('seed-ui3.py').resolve()
code=source.read_text().replace('warehouse_ui3_test','warehouse_r1_test').replace('/tmp/ui3-fixture.json','/tmp/r1-fixture.json')
# The original guard refuses an existing target database, so reruns never reset data.
exec(compile(code,str(source),'exec'),{'__file__':str(source),'__name__':'__main__'})
p=Path('/tmp/r1-fixture.json');data=json.loads(p.read_text());data['database']='warehouse_r1_test';p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
