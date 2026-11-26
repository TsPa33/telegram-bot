"""Import only exact, visually reviewed pilot v4 artifact files; no network or inference."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

# The exact outputs from pilot run 45877387835, inspected on a dark canvas.
# Audi unknown-year match is explicitly model-only, not generation identification.
SPECS=[
 ("alfa-147","Alfa Romeo",["147","147 (937_)","147 937_"],2008,2008,"hatchback",False,
 "35aef1abde11e238a67b18adf06cd662beaeb613d25d5358954cc26588a95d06",
 "File:Alfa Romeo 147 front 20071007.jpg","0870881a90dc0628b10f69dc78b9089328e723ed","Rudolf Stricker","3.0"),
 ("audi-q5","Audi",["Q5"],2008,2017,"suv",True,
 "406bb985932d0ec429546138b2737b57540ab414c71334be8da04f0fc45da5c9",
 "File:Audi Q5 8R.jpg","56e785a0dc6011d45662eb8fca63019c9a8c1f65","Bene Riobó","4.0"),
 ("daf-xf","DAF",["XF 105","XF105"],2007,2007,"unknown",False,
 "21992a92265cbf6d80ddda7bc529bc3189aa760b6729c42ee1ce0bec9c8e5552",
 "File:DAF XF front.jpg","3e55e409c18753c56588bdfca23a06d28e5d25d2","User:MarkusHagenlocher","3.0"),
 ("volvo-xc90","Volvo",["XC90"],2016,2016,"suv",False,
 "03e188983e94ffbf8e09dab625a839f81278eb0dea720ed48ae8e74318b4fb57",
 "File:Volvo XC90 - 2016.jpg","9be0b34794d667f3a2e521d0cbc46c0630aab1da","Staticvent","4.0"),
]
def main():
    p=argparse.ArgumentParser();p.add_argument("artifact",type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    target=root/"src/assets/vehicles"
    report=json.loads((a.artifact/"report.json").read_text())
    assert report["technical_pass"]==4
    by={r["label"]:r for r in report["results"]}
    assets=[];provenance=[];binary={}
    from urllib.parse import quote
    for label,make,models,year_from,year_to,body,unknown,sha,title,source_sha,author,version in SPECS:
        r=by[label];b=(a.artifact/(label+".webp")).read_bytes();source=r["source"]
        assert r["status"]=="technical_pass" and r["webp_sha256"]==sha==hashlib.sha256(b).hexdigest()
        assert source["sha1"]==source_sha and source["title"]==title
        license_name="CC BY-SA "+version;license_url="https://creativecommons.org/licenses/by-sa/"+version+"/"
        assert source["license"]==license_name and source["license_url"]==license_url
        assert source["attribution"]==author+" · фон видалено, WebP"
        assert 0<len(b)<=100000 and b[:4]==b"RIFF" and b[8:16]==b"WEBPVP8X" and b[20]&16
        width=int.from_bytes(b[24:27],"little")+1;height=int.from_bytes(b[27:30],"little")+1
        assert width==r["width"] and height==r["height"] and 0<width<=700 and 0<height<=500
        file="reference-"+label+".webp";binary[file]=b
        source_url="https://commons.wikimedia.org/wiki/"+quote(title.replace(" ","_"),safe=":")
        for i,model in enumerate(models):
            assets.append(dict(id="reference-"+label+("-alias-"+str(i) if i else ""),kind="model",file=file,width=width,height=height,
                manufacturer=make,model=model,yearFrom=year_from,yearTo=year_to,bodyType=body,verified=True,
                referencePhoto=True,transparentCutout=True,allowUnknownYear=unknown,
                source=dict(type="licensed",description="Model reference, not actual donor. Background removed in isolated pilot; pilot-quality staging artwork.",reference=source_url),
                usage=dict(status="approved",license=license_name,licenseUrl=license_url,commercialUse=True,attribution=author+" · фон видалено, WebP")))
        provenance.append(dict(file=file,sha256=sha,bytes=len(b),width=width,height=height,source_title=title,source_sha1=source_sha,source_url=source_url,author=author,license=license_name,license_url=license_url,changes="background removed; cropped; scaled; WebP",pilot_run=45877387835))
    for name,b in binary.items():(target/name).write_bytes(b)
    (target/"model-reference-provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+"\n")
    (root/"src/vehicleModelReferenceAssets.ts").write_text("import type {ImageAsset} from './vehicleImageTypes';\n// Exact pilot assets, reviewed for staging; no runtime AI dependency.\nexport const modelReferenceAssets: readonly ImageAsset[] = "+json.dumps(assets,ensure_ascii=False,indent=2)+";\n")
    print("Imported",len(binary),"unique model references,",sum(len(b) for b in binary.values()),"bytes")
if __name__=="__main__":main()
