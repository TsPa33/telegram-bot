FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
RUN chmod -R a=rX /app && useradd --uid 1000 --create-home warehouse && mkdir -p /data/photos && chown warehouse:warehouse /data/photos
COPY deploy/railway/api-entrypoint.sh /usr/local/bin/warehouse-api-entrypoint
RUN chmod 0755 /usr/local/bin/warehouse-api-entrypoint
ENV PORT=8010 WAREHOUSE_ENV=staging WAREHOUSE_COOKIE_SECURE=true
EXPOSE 8010
ENTRYPOINT ["/usr/local/bin/warehouse-api-entrypoint"]
CMD ["python", "-m", "app.staging"]
