import json
import pytest
from app.services import commons_model_photos as c, model_reference_photos as m

def page(**changes):
    return {"ns":6,"title":"File:Example.jpg","imageinfo":[{"sha1":"a"*40,"mime":"image/jpeg","size":100,
        "url":"https://upload.wikimedia.org/wikipedia/commons/a/ab/Example.jpg",
        "extmetadata":{"License":{"value":"cc-by-sa-4.0"},"LicenseUrl":{"value":"https://creativecommons.org/licenses/by-sa/4.0/"},
                       "Artist":{"value":"<a>Example Author</a>"}},**changes}]}

def test_metadata():
    result=c.metadata(page())
    assert result["license"]=="CC BY-SA 4.0"
    assert result["attribution"].startswith("Example Author")
    for kw in ({"url":"https://evil.test/file"},{"mime":"image/svg+xml"},{"sha1":""},{"extmetadata":{"License":{"value":"nonfree"}}}):
        with pytest.raises(ValueError):c.metadata(page(**kw))

def test_no_review_no_provider_claim(tmp_path):
    i=m.model_identity("Volvo","XC90","",2016)
    j=m.model_identity("Audi","Q5","",None)
    f=tmp_path/"review.json"
    f.write_text(json.dumps([dict(identity=i,title="File:Example.jpg",sha1="a"*40,reviewed=True),
                             dict(identity=j,title="File:Another.jpg",sha1="b"*40,reviewed=False)]))
    conf={"kind":"commons","registry":str(f)}
    db=tmp_path/"lib.sqlite3";m.init(db);m.enqueue(db,[i,j])
    assert c.reviewed_keys(conf)=={m.key_for(i)}
    called=[]
    def fail(_,identity):called.append(identity);raise ValueError("fixture")
    assert m.process_one(db,conf,now=1000,fetch=fail)
    assert not m.process_one(db,conf,now=1001,fetch=fail)
    assert called==[i]
    with m.connect(db,True) as d:
        assert d.execute("SELECT attempts FROM photos WHERE key=?",(m.key_for(j),)).fetchone()[0]==0


def test_cc0_alias_and_deed_url():
    ext={"License":{"value":"cc-zero"},"LicenseUrl":{"value":"http://creativecommons.org/publicdomain/zero/1.0/deed.en"},"Artist":{"value":"Example"}}
    assert c.metadata(page(extmetadata=ext))["license"]=="CC0 1.0"
    ext["LicenseUrl"]["value"]="https://creativecommons.org/licenses/by-nc/4.0/"
    with pytest.raises(ValueError):c.metadata(page(extmetadata=ext))


def test_mask_confident_foreground_and_background():
    import numpy as np
    mask=c.refine_mask(np.array([[0,.1,.4,.8,1.0]],dtype=np.float32))
    assert mask[0,0]==mask[0,1]==0
    assert 0<mask[0,2]<255
    assert mask[0,3]==mask[0,4]==255

def test_large_jpeg_decoder_is_bounded():
    import io
    from PIL import Image
    # 25 MP input, above old cap, must be downsampled before segmentation.
    buf=io.BytesIO()
    Image.new("RGB",(5000,5000),"gray").save(buf,"JPEG")
    image=c.decode_source(buf.getvalue())
    assert image.mode=="RGB" and image.size==(1200,1200)

def test_non_jpeg_pixel_limit_and_animation():
    import io
    from PIL import Image
    buf=io.BytesIO()
    Image.new("1",(5000,5000)).save(buf,"PNG")
    with pytest.raises(ValueError,match="pixel limit"):c.decode_source(buf.getvalue())
    buf=io.BytesIO()
    a=Image.new("RGB",(20,20),"red")
    b=Image.new("RGB",(20,20),"blue")
    a.save(buf,"WEBP",save_all=True,append_images=[b],duration=100)
    with pytest.raises(ValueError,match="animated"):c.decode_source(buf.getvalue())
