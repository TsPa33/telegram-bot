"""Disposable CI pilot: public sources only, no warehouse data, no library writes."""
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import time

from PIL import Image
from app.services import commons_model_photos as c, model_reference_photos as m

MODELS=[
    ("alfa-147","File:Alfa Romeo 147 front.JPG",m.model_identity("Alfa Romeo","147","",2008)),
    ("audi-q5","File:Audi Q5 8R.jpg",m.model_identity("Audi","Q5","",None)),
    ("daf-xf","File:DAF XF front.jpg",m.model_identity("DAF","XF 105","",2007)),
    ("volvo-xc90","File:Volvo XC90 - 2016.jpg",m.model_identity("Volvo","XC90","",2016)),
]
def main():
    out=Path(os.environ["PHOTO_PILOT_OUTPUT"]);out.mkdir(parents=True,exist_ok=True)
    weights=Path(os.environ["PHOTO_PILOT_WEIGHT"])
    digest=hashlib.sha256(weights.read_bytes()).hexdigest()
    config={"weight":str(weights),"digest":digest}
    summary={"scope":"public test fixtures, not verified donor images; no library publication",
             "model_sha256":digest,"results":[]}
    try:
        with c.client() as client:
            for label,title,identity in MODELS:
                result={"label":label,"identity":identity,"title":title,"status":"failed","phase":"metadata"}
                begin=time.monotonic()
                try:
                    pages=c.api_query(client,{"titles":title,"prop":"imageinfo","iiprop":"url|sha1|mime|size|extmetadata","iilimit":1})
                    if len(pages)!=1:raise ValueError("ambiguous source")
                    source=c.metadata(pages[0])
                    result["source"]={k:v for k,v in source.items() if k!="url"}
                    if source["title"]!=title:raise ValueError("file title mismatch")
                    result["phase"]="download"
                    if not 0<source["size"]<=c.MAX_DOWNLOAD:raise ValueError("source too large")
                    raw=c.bounded_get(client,source["url"],c.MAX_DOWNLOAD)
                    if hashlib.sha1(raw).hexdigest()!=source["sha1"]:raise ValueError("source hash mismatch")
                    result["download_bytes"]=len(raw)
                    result["phase"]="segment"
                    start=time.monotonic()
                    cutout=c.segment(config,raw)
                    result["inference_seconds"]=round(time.monotonic()-start,3)
                    result["phase"]="validate_webp"
                    final=m.prepare_cutout(cutout)
                    with Image.open(io.BytesIO(final)) as im:
                        alpha=im.convert("RGBA").getchannel("A")
                        hist=alpha.histogram()
                        result.update(width=im.width,height=im.height,transparent_fraction=round(hist[0]/(im.width*im.height),3))
                    (out/(label+".webp")).write_bytes(final)
                    result.update(status="technical_pass",phase="complete",webp_bytes=len(final),webp_sha256=hashlib.sha256(final).hexdigest())
                except Exception as exc:
                    result["error_type"]=type(exc).__name__
                    result["error"]=str(exc)[:300]
                finally:
                    result["total_seconds"]=round(time.monotonic()-begin,3)
                    result["peak_rss_mib"]=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)
                    summary["results"].append(result)
                    print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        summary["technical_pass"]=sum(r["status"]=="technical_pass" for r in summary["results"])
        (out/"report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if summary["technical_pass"]!=len(MODELS):raise SystemExit(1)
if __name__=="__main__":main()
