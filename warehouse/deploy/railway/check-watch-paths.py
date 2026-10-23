"""Read-only proof of Docker COPY coverage and backend/frontend path isolation."""
import fnmatch
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
WAREHOUSE = REPO / 'warehouse'
services = json.loads((ROOT / 'services.json').read_text())['services']
files = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','warehouse'],cwd=REPO,text=True).splitlines()


def matches(service, path):
    return any(fnmatch.fnmatchcase('/'+path.lstrip('/'), pattern) for pattern in services[service]['watchPaths'])


for name in ['warehouse-api','warehouse-web']:
    docker = WAREHOUSE / services[name]['dockerfilePath']
    inputs = {str(docker.relative_to(REPO)), 'warehouse/.dockerignore'}
    for line in docker.read_text().splitlines():
        if not line.startswith('COPY ') or '--from=' in line:
            continue
        for source in shlex.split(line)[1:-1]:
            path = WAREHOUSE/source
            assert path.exists(), source
            relative = str(path.relative_to(REPO))
            if path.is_dir():
                inputs.update(f for f in files if f.startswith(relative+'/'))
                inputs.add(relative+'/__future_build_input__')
            else:
                inputs.add(relative)
    for path in inputs:
        assert matches(name,path), (name,'unwatched build dependency',path)
    print(f'PASS {name}: all Dockerfile/COPY inputs, future directory files and .dockerignore watched')

for path in files:
    if path.startswith('warehouse/backend/'):
        assert matches('warehouse-api',path) and not matches('warehouse-web',path), path
    if path.startswith('warehouse/frontend/'):
        assert matches('warehouse-web',path) and not matches('warehouse-api',path), path
for path in ['warehouse/deploy/railway/services.json','warehouse/STAGED_AUTO_DEPLOY.md','warehouse/DISMANTLING.md']:
    assert not matches('warehouse-api',path) and not matches('warehouse-web',path), path
assert matches('warehouse-api','warehouse/.dockerignore') and matches('warehouse-web','warehouse/.dockerignore')
changed = subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=REPO,text=True).splitlines()
assert 'warehouse/.dockerignore' not in changed, 'Shared build input changed: two-stage publication needs separate coordination'
print('PASS: backend-only changes cannot trigger web; frontend-only changes cannot trigger API; docs/template do not trigger either')
print('Shared .dockerignore triggers BOTH: keep unchanged in this staged rollout. Dashboard must already contain these patterns; services.json is not Railway IaC.')
