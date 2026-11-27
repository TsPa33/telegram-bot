import base64
import io
from PIL import Image, ImageDraw
import pytest
from app.services import model_reference_photos as m

def png(alpha=True):
    im=Image.new("RGBA" if alpha else "RGB",(100,70),(0,0,0,0) if alpha else (230,230,230))
    ImageDraw.Draw(im).rectangle((15,10,85,60),fill=(100,120,130,255) if alpha else (100,120,130))
    out=io.BytesIO();im.save(out,"PNG");return out.getvalue()

def response(identity):
    return dict(identity=identity,kind="real_photo",commercial_use=True,derivatives_allowed=True,
                identity_reviewed=True,source_url="https://example.test/source",license_url="https://example.test/license",
                attribution="Test fixture",license="Fixture only",image_base64=base64.b64encode(png()).decode())

def test_identity_and_dedup(tmp_path):
    i=m.model_identity("VOLVO","XC90","II",2016)
    assert i==m.model_identity(" volvo ","xc90","ii",2016)
    assert m.key_for(i)!=m.key_for(m.model_identity("Volvo","XC90","I",2016))
    p=tmp_path/"library.sqlite3";m.init(p);m.enqueue(p,[i,i])
    assert m.process_one(p,("test","test"),now=1000,fetch=lambda _,identity:response(identity))
    assert not m.process_one(p,("test","test"),now=1001,fetch=lambda *_:pytest.fail("duplicate"))
    with m.connect(p,True) as db:
        r=db.execute("SELECT state,image FROM photos").fetchone()
        assert r["state"]=="ready" and r["image"][:4]==b"RIFF"

def test_alpha_and_identity_checks():
    with pytest.raises(ValueError):m.prepare_cutout(png(False))
    i=m.model_identity("DAF","XF 105","",2007)
    for change in ({"commercial_use":False},{"kind":"generated"},{"identity":{}},{"derivatives_allowed":False},{"identity_reviewed":False}):
        with pytest.raises(ValueError):m.validate_result(i,{**response(i),**change})

def test_rate_limit_and_retry(tmp_path):
    p=tmp_path/"library.sqlite3";m.init(p)
    m.enqueue(p,[m.model_identity("Fixture",str(x),"",2000) for x in range(15)])
    calls=[]
    def fail(*args):
        calls.append(1);raise ValueError("fixture")
    for _ in range(20):m.process_one(p,("test","test"),now=1000,fetch=fail)
    assert len(calls)==m.DAILY_LIMIT
    assert not m.process_one(p,None,now=90000,fetch=fail)
    with m.connect(p,True) as db:assert db.execute("SELECT SUM(attempts) FROM photos").fetchone()[0]==m.DAILY_LIMIT

def test_default_off(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_MODEL_PHOTO_ENABLED",raising=False)
    assert m.library_path() is None
    stop,thread=m.start_worker()
    assert thread is None
