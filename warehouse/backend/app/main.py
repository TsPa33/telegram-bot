from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi import HTTPException
from app.config import allowed_hosts, is_staging, public_origin, secure_cookies
from app.api.routes import router
from app.api.plan_parts import router as plan_parts_router
from app.api.checklists import router as checklists_router
from app.api.dismantling import router as dismantling_router
from app.api.orders import router as orders_router
from app.db import engine

app = FastAPI(
    title="CarPot Warehouse API",
    version="1.0.0",
    description="Standalone tenant-isolated warehouse. All business endpoints require a session cookie; mutations also require X-CSRF-Token. Monetary values use explicit UAH/USD currencies without automatic conversion. No CarPot production integration.",
)
app.include_router(router)
app.include_router(plan_parts_router)
app.include_router(checklists_router)
app.include_router(dismantling_router)
app.include_router(orders_router)
from app.api.workshop import router as workshop_router
app.include_router(workshop_router)
if is_staging():
    if not secure_cookies():
        raise RuntimeError("Staging requires secure cookies")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts(),
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Конфлікт даних: перевірте унікальні ідентифікатори та обмеження залишків"
        },
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if is_staging() and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") != public_origin():
            return JSONResponse(
                status_code=403, content={"detail": "Недійсне джерело запиту"}
            )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health", tags=["Health"])
def health():
    from app.staging import migration_heads

    try:
        with engine().connect() as conn:
            versions = frozenset(
                conn.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )
        if versions != migration_heads():
            raise HTTPException(
                503, "Warehouse migrations are not at the expected version"
            )
    except SQLAlchemyError:
        raise HTTPException(503, "Warehouse database is not ready") from None
    return {"status": "ok"}
