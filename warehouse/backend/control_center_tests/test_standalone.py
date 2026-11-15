from fastapi.testclient import TestClient
from app.control_center.asgi import create_standalone


def test_standalone_has_only_staff_routes_and_static(tmp_path, monkeypatch):
    (tmp_path / "control").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "control" / "index.html").write_text("<html>Control Center</html>")
    (tmp_path / "assets" / "test.js").write_text("/* test */")
    with TestClient(create_standalone(tmp_path), base_url="http://testserver") as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/", follow_redirects=False).headers["location"] == "/control/"
        assert client.get("/control/").status_code == 200
        assert client.get("/assets/test.js").status_code == 200
        assert client.get("/api/control/status").status_code == 200
        assert client.get("/api/control/companies").status_code == 401
        assert client.get("/api/v1/auth/options").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/control/", headers={"Host":"evil.example"}).status_code == 421
        assert client.get("/health", headers={"Host":"healthcheck.railway.app"}).status_code == 200
        assert client.get("/control/", headers={"Host":"healthcheck.railway.app"}).status_code == 421
        assert "frame-ancestors 'none'" in client.get("/control/").headers["content-security-policy"]
        monkeypatch.setenv("CONTROL_CENTER_ENABLED", "false")
        assert client.get("/control/").status_code == 404
        assert client.get("/api/control/status").status_code == 404


def test_standalone_readiness_fails_closed(tmp_path, monkeypatch):
    with TestClient(create_standalone(tmp_path), base_url="http://testserver") as client:
        assert client.get("/health").status_code == 503
        (tmp_path / "control").mkdir()
        (tmp_path / "assets").mkdir()
        (tmp_path / "control" / "index.html").write_text("test")
        monkeypatch.delenv("CONTROL_CENTER_MFA_KEY")
        assert client.get("/health").status_code == 503
        assert "CONTROL_CENTER_MFA_KEY" not in client.get("/health").text
