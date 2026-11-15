import time
from sqlalchemy import select
from app.control_center.models import Audit, Staff
from app.control_center.security import totp
from test_support import authenticate, SECRET

def test_rotate_requires_both_mfa_codes_and_revokes_session(client, staff_factory, db, monkeypatch):
    stamp=time.time()
    monkeypatch.setattr(time,"time",lambda:stamp)
    owner=staff_factory()
    step=int(time.time())//30
    authenticate(client,owner,step=step-1)
    enroll=client.post("/api/control/auth/enrollment").json()
    body=dict(current_password="long-staff-test-password",current_code=totp(SECRET,step),new_password="new-owner-password-long",new_code=totp(enroll["seed"],step-1),enrollment=enroll["enrollment"])
    assert client.post("/api/control/auth/rotate",json={**body,"new_code":"xxxxxx"}).status_code==422
    assert client.post("/api/control/auth/rotate",json=body).status_code==204
    assert client.get("/api/control/auth/me").status_code==401
    assert client.post("/api/control/auth/login",json=dict(username=owner.username,password=body["current_password"],code=totp(SECRET,step))).status_code==401
    response=client.post("/api/control/auth/login",json=dict(username=owner.username,password=body["new_password"],code=totp(enroll["seed"],step)))
    assert response.status_code==200,response.text
    assert db.scalar(select(Audit.id).where(Audit.permission=="auth.rotate",Audit.actor==owner.id))
