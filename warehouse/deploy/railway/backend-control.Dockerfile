# Dedicated staff-only runtime; root repository build context.
FROM node:22-alpine AS web
WORKDIR /build
COPY warehouse/frontend/package.json warehouse/frontend/package-lock.json ./
RUN npm ci
COPY warehouse/frontend/tsconfig.json warehouse/frontend/vite.control.config.ts ./
COPY warehouse/frontend/control ./control
COPY warehouse/frontend/src ./src
RUN npx tsc -b && npx vite build --config vite.control.config.ts

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY warehouse/backend/requirements-control-center.lock ./requirements-control-center.lock
# Railway builder supports cache mounts, not BuildKit secret mounts.
# Public PyPI TLS verification and the locked artifact hashes remain mandatory.
RUN pip install --require-hashes -r requirements-control-center.lock
COPY warehouse/backend/app ./app
COPY warehouse/backend/control_center_migrations ./control_center_migrations
COPY warehouse/backend/alembic ./alembic
COPY warehouse/backend/alembic.ini ./alembic.ini
COPY bot/billing/__init__.py bot/billing/models.py bot/billing/transport.py ./bot/billing/
COPY --from=web /build/dist-control /app/control-web
RUN useradd --uid 10001 --create-home warehouse && chown -R warehouse:warehouse /app
USER warehouse
# No customer startup, automatic migration, provisioning or synchronization.
CMD ["sh", "-c", "exec uvicorn app.control_center.asgi:app --host 0.0.0.0 --port ${PORT:-8010}"]
