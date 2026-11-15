# Prepared image, root repository build context. No deployment performed.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY warehouse/backend/requirements-control-center.lock ./requirements-control-center.lock
RUN --mount=type=secret,id=warehouse_ca,required=false \
    if [ -f /run/secrets/warehouse_ca ]; then export PIP_CERT=/run/secrets/warehouse_ca; fi; \
    pip install --require-hashes -r requirements-control-center.lock
COPY warehouse/backend/app ./app
COPY warehouse/backend/control_center_migrations ./control_center_migrations
COPY warehouse/backend/alembic ./alembic
COPY warehouse/backend/alembic.ini ./alembic.ini
COPY bot/billing/__init__.py bot/billing/models.py bot/billing/transport.py ./bot/billing/
RUN useradd --uid 10001 --create-home warehouse && mkdir -p /data/photos && chown -R warehouse:warehouse /app /data/photos
USER warehouse
# No implicit migration/provision/synchronization. Dedicated ASGI can be selected
# after extraction; for shared Warehouse readiness use the existing /health.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
