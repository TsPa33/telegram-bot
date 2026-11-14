FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY warehouse/backend/requirements.lock ./requirements.lock
RUN pip install --require-hashes -r requirements.lock
COPY warehouse/backend/app ./app
COPY warehouse/backend/alembic ./alembic
COPY warehouse/backend/alembic.ini ./alembic.ini
COPY bot/billing/__init__.py bot/billing/models.py bot/billing/transport.py ./bot/billing/
RUN useradd --uid 10001 --create-home warehouse && mkdir -p /data/photos && chown -R warehouse:warehouse /data
USER warehouse
CMD ["sh","-c","exec python -m app.staging"]
