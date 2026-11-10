"""Synthetic ZIP/CSV files only; no private source copied into Git."""
import hashlib,importlib.util,json,shutil,subprocess,sys,zipfile
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('resume_inputs',Path(__file__).resolve().parents[2]/'scripts/inspect_resume_inputs.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_manifest_verified_before_temp_extraction(tmp_path):
    body=b'local synthetic PRD data';archive=tmp_path/'source.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('MANIFEST.json',json.dumps({'files':{'prd.csv':hashlib.sha256(body).hexdigest()}}));z.writestr('prd.csv',body)
    result=module.verify(archive);folder=Path(result['directory'])
    try:assert (folder/'prd.csv').read_bytes()==body and not folder.is_relative_to(Path(__file__).resolve().parents[3])
    finally:shutil.rmtree(folder)

@pytest.mark.parametrize('name,checksum',[('../escape.csv','0'*64),('prd.csv','0'*64)])
def test_unsafe_path_or_bad_checksum_rejected(tmp_path,name,checksum):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('MANIFEST.json',json.dumps({'files':{name:checksum}}));z.writestr(name,b'content')
    with pytest.raises(ValueError):module.verify(archive)


def test_offline_csv_compiler_keeps_id_and_does_not_approve(tmp_path):
    source=tmp_path/'prd.csv';source.write_text('id;description;normalizeddescription;assemblygroupdescription;usagedescription\n1;Оливний фільтр;Фільтр;Двигун;\n2;Паливний фільтр;Фільтр;Двигун;\n',encoding='utf-8-sig')
    output=tmp_path/'prepared.json'
    subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/prepare_universal_catalogue.py'),'--input',str(source),'--output',str(output),'--batch-dir',str(tmp_path/'batches')],check=True,capture_output=True)
    result=json.loads(output.read_text());assert result['counts']['source_records']==2 and result['counts']['physical_types']==0
    request=json.loads((tmp_path/'batches/preview-00001.json').read_text());assert len(request['rows'])==2 and request['reviews']==[]
    assert {r['source_key'] for r in result['review']}=={'td1q2018:prd:1','td1q2018:prd:2'}
