"""Dedicated Control Center entry: staff API and compiled UI, no Warehouse startup."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.staticfiles import StaticFiles

from .api import create_app
from .config import cipher, connection, enabled, environment, origin


def create_standalone(static_dir=None):
    root = Path(static_dir or os.getenv("CONTROL_CENTER_STATIC_DIR", "/app/control-web"))
    app = FastAPI(title="CarPot Control Center", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/api/control", create_app())
    app.mount("/assets", StaticFiles(directory=root / "assets", check_dir=False))

    @app.middleware("http")
    async def perimeter(request: Request, call_next):
        if not enabled():
            return JSONResponse({"detail": "Not found"}, status_code=404)
        try:
            expected = urlsplit(origin()).netloc.lower()
        except (KeyError, RuntimeError, ValueError):
            return JSONResponse({"detail": "Control Center unavailable"}, status_code=503)
        host = request.headers.get("host", "").lower()
        # Only the Railway health checker may use its special Host header.
        health_host = request.url.path == "/health" and host.split(":")[0] == "healthcheck.railway.app"
        if host != expected and not health_host:
            return JSONResponse({"detail": "Invalid host"}, status_code=421)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
        })
        return response

    @app.get("/health")
    def health():
        # Readiness never migrates, provisions staff, syncs Warehouse or calls Billing.
        try:
            cipher()
            if not (root / "control" / "index.html").is_file() or not (root / "assets").is_dir():
                raise RuntimeError("UI artifact missing")
            with connection().connect() as db:
                version = db.execute(text("SELECT version,environment FROM control_center.schema_version")).one()
                if tuple(version) != ("001", environment()):
                    raise RuntimeError("Schema mismatch")
            return {"status": "ok"}
        except (KeyError, ValueError, RuntimeError, SQLAlchemyError):
            return JSONResponse({"detail": "Control Center not ready"}, status_code=503)

    @app.get("/")
    @app.get("/control")
    def entry():
        return RedirectResponse("/control/", status_code=307)

    @app.get("/control/")
    def control_page():
        html = root / "control" / "index.html"
        if not html.is_file():
            return JSONResponse({"detail": "Control Center not ready"}, status_code=503)
        return FileResponse(html, media_type="text/html")

    return app


app = create_standalone()
