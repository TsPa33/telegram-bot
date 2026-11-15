SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def authenticate(client, staff, step=None):
    import time
    from app.control_center.security import totp

    code = totp(SECRET, step or int(time.time()) // 30)
    r = client.post(
        "/api/control/auth/login",
        json=dict(
            username=staff.username, password="long-staff-test-password", code=code
        ),
    )
    assert r.status_code == 200, r.text
    client.headers["X-Control-CSRF"] = r.json()["csrf"]
    return r
