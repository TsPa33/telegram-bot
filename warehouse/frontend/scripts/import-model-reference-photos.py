#!/usr/bin/env python3
"""Maintainer-only: download fixed Commons candidates, inspect, then import local WebP.
Requires Pillow. No live Warehouse API or database access."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    dict(id="alfa-147", manufacturer="Alfa Romeo", models=["147", "147 (937_)"],
         years=[2005, 2010], body="hatchback", file="Alfa_Romeo_147_front.JPG",
         author="Tokumeigakarinoaoshima", license="CC0 1.0", license_url="https://creativecommons.org/publicdomain/zero/1.0/"),
    dict(id="audi-q5-8r", manufacturer="Audi", models=["Q5", "Q5 (8R)"],
         years=[2008, 2017], body="suv", file="Audi_Q5_8R.jpg",
         author="Bene Riobó", license="CC BY-SA 4.0", license_url="https://creativecommons.org/licenses/by-sa/4.0/"),
    dict(id="daf-xf105", manufacturer="DAF", models=["XF 105", "XF105"],
         years=[2006, 2013], body="unknown", file="DAF_XF_front.jpg",
         author="MarkusHagenlocher", license="CC BY-SA 3.0", license_url="https://creativecommons.org/licenses/by-sa/3.0/",
         sha1="3e55e409c18753c56588bdfca23a06d28e5d25d2"),
    dict(id="volvo-xc90-ii", manufacturer="Volvo", models=["XC90", "XC90 II"],
         years=[2016, 2019], body="suv", file="Volvo_XC90_-_2016.jpg",
         author="Staticvent", license="CC BY-SA 4.0", license_url="https://creativecommons.org/licenses/by-sa/4.0/"),
]
MAX_BYTES = 15 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 35_000_000

def download(c):
    name = c["file"]
    digest = hashlib.md5(name.encode("utf-8"), usedforsecurity=False).hexdigest()
    url = "https://upload.wikimedia.org/wikipedia/commons/" + digest[0] + "/" + digest[:2] + "/" + quote(name)
    request = Request(url, headers={"User-Agent": "CarPotReferencePhotoImport/1.0 (maintainer-operated; https://github.com/TsPa33/telegram-bot)"})
    with urlopen(request, timeout=30) as r:
        if not r.geturl().startswith("https://upload.wikimedia.org/"):
            raise ValueError("Unexpected source redirect")
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or not raw:
        raise ValueError("Invalid image size")
    if c.get("sha1") and hashlib.sha1(raw).hexdigest() != c["sha1"]:
        raise ValueError("Original SHA-1 mismatch")
    return raw

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--review-dir", required=True, type=Path)
    p.add_argument("--approve", nargs="+", choices=[c["id"] for c in CANDIDATES],
                   help="Explicitly approve inspected candidate IDs; without this, only download for review.")
    args = p.parse_args()
    args.review_dir.mkdir(parents=True, exist_ok=True)
    if not args.approve:
        for c in CANDIDATES:
            raw = download(c)
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            (args.review_dir / c["file"]).write_bytes(raw)
            print(c["id"], hashlib.sha256(raw).hexdigest(), c["license"], c["author"])
        print("Inspect photographs and their Commons source/license before running --approve.")
        return
    selected = [c for c in CANDIDATES if c["id"] in args.approve]
    assets = []
    prepared = {}
    provenance = []
    for c in selected:
        raw = (args.review_dir / c["file"]).read_bytes()
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError("Invalid reviewed image size")
        if c.get("sha1") and hashlib.sha1(raw).hexdigest() != c["sha1"]:
            raise ValueError("Reviewed image SHA-1 mismatch")
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != "JPEG":
                raise ValueError("Expected original JPEG")
            # Original JPEG is retained for provenance. Require separately reviewed alpha cutout.
            cutout_path=args.review_dir/(c['id']+'-cutout.png')
            if not cutout_path.is_file(): raise ValueError('Reviewed transparent cutout required: '+str(cutout_path))
            with Image.open(cutout_path) as cutout:
                if cutout.mode!='RGBA' or cutout.getchannel('A').histogram()[0] < cutout.width*cutout.height*0.08: raise ValueError('Real alpha transparency required')
                photo=cutout.copy()
            photo.thumbnail((640, 480))
            buf = io.BytesIO()
            photo.save(buf, "WEBP", quality=78, method=6)
            data = buf.getvalue()
            if len(data) > 100_000:
                raise ValueError("Optimized image exceeds size target")
            width, height = photo.size
        filename = "reference-" + c["id"] + ".webp"
        prepared[filename] = data
        page = "https://commons.wikimedia.org/wiki/File:" + quote(c["file"])
        for i, model in enumerate(c["models"]):
            assets.append(dict(id=c["id"]+"-"+str(i),kind="model",manufacturer=c["manufacturer"],
              model=model,yearFrom=c["years"][0],yearTo=c["years"][1],bodyType=c["body"],
              file=filename,width=width,height=height,verified=True,referencePhoto=True,allowUnknownYear=True,transparentCutout=True,
              source=dict(type="licensed",description="Reviewed real model photograph; background removed, resized, WebP conversion; not donor or trim verification.",reference=page),
              usage=dict(status="approved",license=c["license"],licenseUrl=c["license_url"],commercialUse=True,
                         attribution=c["author"]+" · видалено фон, змінено розмір, WebP")))
        provenance.append(dict(id=c["id"], source=page, author=c["author"], license=c["license"],
                               license_url=c["license_url"], original_sha256=hashlib.sha256(raw).hexdigest(),
                               asset=filename, asset_sha256=hashlib.sha256(data).hexdigest(),
                               width=width,height=height,bytes=len(data),changes="background removed, resize, WebP conversion"))
    target=ROOT/"src"/"assets"/"vehicles"
    manifest=ROOT/"src"/"vehicleModelReferenceAssets.ts"
    # Only write after every selected candidate has validated. Full selection replaces generated registry.
    for name,data in prepared.items():
        (target/name).write_bytes(data)
    manifest.write_text("import type {ImageAsset} from './vehicleImageTypes';\nexport const modelReferenceAssets: readonly ImageAsset[] = "+json.dumps(assets,ensure_ascii=False,indent=2)+";\n",encoding="utf-8")
    (target/"model-reference-provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Generated",len(assets),"model entries for",len(prepared),"reviewed local photos. Review git diff and commit explicitly.")

if __name__ == "__main__":
    main()
