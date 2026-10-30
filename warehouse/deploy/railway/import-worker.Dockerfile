FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
RUN chmod -R a=rX /app && useradd --uid 1000 --create-home warehouse
USER warehouse
ENV WAREHOUSE_ENV=staging
CMD ["python", "-m", "app.import_worker"]
