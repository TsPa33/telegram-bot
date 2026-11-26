"""Wikimedia Commons reviewed-source adapter and local background removal.

Search results are candidates, never proof of vehicle identity. Operator-reviewed
file revision + exact model identity are mandatory before automatic publication.
No donor identifiers or customer text beyond reviewed model fields leave CarPot.
"""
import base64
from functools import lru_cache
import hashlib
from html import unescape
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit, quote

API="https://commons.wikimedia.org/w/api.php"
LICENSES={
    "cc0-1.0":("CC0 1.0","https://creativecommons.org/publicdomain/zero/1.0/"),
    "cc-by-4.0":("CC BY 4.0","https://creativecommons.org/licenses/by/4.0/"),
    "cc-by-sa-4.0":("CC BY-SA 4.0","https://creativecommons.org/licenses/by-sa/4.0/"),
    "cc-by-3.0":("CC BY 3.0","https://creativecommons.org/licenses/by/3.0/"),
    "cc-by-sa-3.0":("CC BY-SA 3.0","https://creativecommons.org/licenses/by-sa/3.0/"),
}
MAX_DOWNLOAD=12*1024*1024

class Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
    def handle_data(self,data):self.parts.append(data)

def plain(value):
    p=Plain()
    p.feed(str(value or "")[:8000])
    return " ".join(unescape(" ".join(p.parts)).split())

def exact_host(url,host):
    try:
        p=urlsplit(url)
        return p.scheme=="https" and p.netloc==host and not p.username and not p.password
    except (TypeError,ValueError):return False

def client():
    import httpx
    agent=os.environ.get("WAREHOUSE_COMMONS_USER_AGENT","")
    if not agent.startswith("CarPot/") or not ("https://" in agent or "@" in agent):
        raise ValueError("Configure meaningful Wikimedia contact User-Agent")
    return httpx.Client(timeout=httpx.Timeout(20,connect=5),follow_redirects=False,trust_env=False,headers={"User-Agent":agent})

def bounded_get(c,url,limit,params=None):
    with c.stream("GET",url,params=params) as r:
        r.raise_for_status()
        out=bytearray()
        for chunk in r.iter_bytes():
            out.extend(chunk)
            if len(out)>limit:raise ValueError("oversize response")
    return bytes(out)

def api_query(c,params):
    data=json.loads(bounded_get(c,API,2_000_000,{"action":"query","format":"json","formatversion":2,"maxlag":5,**params}))
    if "error" in data:raise ValueError("Commons API error")
    return data.get("query",{}).get("pages",[])

def metadata(page):
    if page.get("ns")!=6 or not page.get("title","").startswith("File:"):raise ValueError("not a file")
    infos=page.get("imageinfo") or []
    if len(infos)!=1:raise ValueError("missing image metadata")
    info=infos[0]; ext=info.get("extmetadata",{})
    def field(name):return ext.get(name,{}).get("value","")
    # Only explicit allowlisted free licenses. No inferred copyright or fair use.
    license_id=str(field("License")).strip().lower()
    # Commons uses cc-zero for CC0 in some extmetadata records.
    if license_id in ("cc-zero","cc0","cc0-1.0"):license_id="cc0-1.0"
    if license_id not in LICENSES:raise ValueError("unsupported license")
    label,license_url=LICENSES[license_id]
    actual=str(field("LicenseUrl")).strip().replace("http://","https://",1).rstrip("/")
    # Deed language variants are the same license, not additional grants.
    actual=re.sub(r"/deed(?:\.[a-zA-Z_-]+)?$","",actual)
    if actual!=license_url.rstrip("/"):raise ValueError("license URL mismatch")
    author=plain(field("Artist"))
    if not author or len(author)>180:raise ValueError("missing or oversized author credit")
    if plain(field("Restrictions")):raise ValueError("additional restrictions require separate review")
    if info.get("mime") not in ("image/jpeg","image/png","image/webp"):raise ValueError("not raster photo")
    if not re.fullmatch("[a-f0-9]{40}",str(info.get("sha1",""))):raise ValueError("missing revision")
    url=info.get("url","")
    if not exact_host(url,"upload.wikimedia.org") or not urlsplit(url).path.startswith("/wikipedia/commons/"):raise ValueError("unexpected source host")
    return dict(title=page["title"],sha1=info["sha1"],url=url,size=info.get("size",0),
                source_url="https://commons.wikimedia.org/wiki/"+quote(page["title"].replace(" ","_"),safe=":"),
                attribution=author+" · фон видалено, WebP",license=label,license_url=license_url)

def discover(c,identity):
    # This is an operator tool: no automatic publication from full-text matches.
    query=" ".join(str(identity.get(k) or "") for k in ("manufacturer","model","generation","year")).strip()
    if len(query)>250 or not query:raise ValueError("invalid query")
    pages=api_query(c,{"generator":"search","gsrnamespace":6,"gsrsearch":query,"gsrlimit":8,
        "prop":"imageinfo","iiprop":"url|sha1|mime|size|extmetadata","iilimit":1})
    candidates=[]
    for p in pages:
        try:candidates.append(metadata(p))
        except (ValueError,TypeError,KeyError):continue
    return candidates

def registry(config):
    from app.services.model_reference_photos import model_identity,key_for
    path=Path(config["registry"])
    if path.stat().st_size>1_000_000:raise ValueError("registry too large")
    records=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records,list) or len(records)>500:raise ValueError("registry must contain <=500 records")
    result={}
    for r in records:
        if r.get("reviewed") is not True:continue
        i=r["identity"]
        normal=model_identity(i["manufacturer"],i["model"],i.get("generation"),i.get("year"))
        if not normal or not str(r.get("title","")).startswith("File:") or not re.fullmatch("[a-f0-9]{40}",r.get("sha1","")):raise ValueError("invalid reviewed record")
        key=key_for(normal)
        if key in result:raise ValueError("duplicate reviewed identity")
        result[key]=r
    return result

def reviewed_keys(config):
    return set(registry(config))

def settings():
    if os.getenv("WAREHOUSE_COMMONS_APPROVED")!="true" or os.getenv("WAREHOUSE_CUTOUT_MODEL_LICENSE_APPROVED")!="true":return None
    path=os.getenv("WAREHOUSE_COMMONS_REVIEW_REGISTRY","")
    weight=os.getenv("WAREHOUSE_CUTOUT_ONNX_PATH","")
    digest=os.getenv("WAREHOUSE_CUTOUT_ONNX_SHA256","")
    if not path or not weight or not re.fullmatch("[a-f0-9]{64}",digest):return None
    if not Path(path).is_absolute() or not Path(weight).is_absolute() or not Path(path).is_file() or not Path(weight).is_file():return None
    if not os.getenv("WAREHOUSE_COMMONS_USER_AGENT","").startswith("CarPot/"):return None
    return dict(kind="commons",registry=path,weight=weight,digest=digest)

@lru_cache(maxsize=1)
def session(path,digest):
    # Explicit pinned local U2NET/U2NETP-compatible ONNX. No model downloads or remote code.
    import onnxruntime as ort
    if Path(path).stat().st_size>250_000_000:raise ValueError("weight too large")
    with open(path,"rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=digest:raise ValueError("weight digest mismatch")
    opts=ort.SessionOptions();opts.intra_op_num_threads=1;opts.inter_op_num_threads=1
    opts.enable_cpu_mem_arena=False
    opts.enable_mem_pattern=False
    return ort.InferenceSession(path,sess_options=opts,providers=["CPUExecutionProvider"])

def refine_mask(pred):
    import numpy as np
    norm=(pred-pred.min())/(pred.max()-pred.min())
    return (np.clip((norm-.15)/(.68-.15),0,1)*255).astype("uint8")

def segment(config,raw):
    import numpy as np
    from PIL import Image,ImageOps
    with Image.open(io.BytesIO(raw)) as im:
        if im.width*im.height>24_000_000 or getattr(im,"n_frames",1)!=1:raise ValueError("oversized or animated source")
        image=ImageOps.exif_transpose(im).convert("RGB")
        image.thumbnail((1200,1200))
    inp=np.asarray(image.resize((320,320),Image.Resampling.LANCZOS),dtype=np.float32)/255.0
    inp=(inp-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
    sess=session(config["weight"],config["digest"])
    pred=np.squeeze(sess.run(None,{sess.get_inputs()[0].name:inp.transpose(2,0,1)[None]})[0])
    if pred.ndim!=2 or not np.isfinite(pred).all() or pred.max()-pred.min()<.01:raise ValueError("invalid mask")
    # Suppress faint background remnants and keep confident vehicle pixels opaque.
    # Pilot tuning, not proof of semantic accuracy. Review resulting wheels/mirrors.
    alpha=Image.fromarray(refine_mask(pred)).resize(image.size,Image.Resampling.LANCZOS)
    rgba=image.convert("RGBA");rgba.putalpha(alpha)
    out=io.BytesIO();rgba.save(out,"WEBP",quality=87)
    return out.getvalue()

def fetch_reviewed(config,identity):
    from app.services.model_reference_photos import key_for
    r=registry(config).get(key_for(identity))
    if not r:raise ValueError("no reviewed photo")
    with client() as c:
        pages=api_query(c,{"titles":r["title"],"prop":"imageinfo","iiprop":"url|sha1|mime|size|extmetadata","iilimit":1})
        if len(pages)!=1:raise ValueError("ambiguous source")
        m=metadata(pages[0])
        if m["title"]!=r["title"] or m["sha1"]!=r["sha1"]:raise ValueError("source revision changed")
        if not isinstance(m["size"],int) or not 0<m["size"]<=MAX_DOWNLOAD:raise ValueError("source too large")
        raw=bounded_get(c,m["url"],MAX_DOWNLOAD)
        if hashlib.sha1(raw).hexdigest()!=m["sha1"]:raise ValueError("download revision mismatch")
    image=segment(config,raw)
    return dict(identity=identity,kind="real_photo",commercial_use=True,derivatives_allowed=True,identity_reviewed=True,
        source_url=m["source_url"],license_url=m["license_url"],license=m["license"],attribution=m["attribution"],
        image_base64=base64.b64encode(image).decode())

def main():
    import argparse
    from app.services.model_reference_photos import model_identity
    p=argparse.ArgumentParser(description="Find Commons photo candidates; no publication or database writes")
    p.add_argument("manufacturer");p.add_argument("model");p.add_argument("--generation",default="");p.add_argument("--year",type=int)
    a=p.parse_args();identity=model_identity(a.manufacturer,a.model,a.generation,a.year)
    if not identity:p.error("invalid model")
    with client() as c:
        candidates=discover(c,identity)
    print(json.dumps({"identity":identity,"candidates":candidates},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
