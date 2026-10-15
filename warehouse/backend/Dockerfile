FROM python:3.11.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock .
RUN --mount=type=secret,id=warehouse_ca,required=false \
    if [ -f /run/secrets/warehouse_ca ]; then export PIP_CERT=/run/secrets/warehouse_ca; fi; \
    pip install --require-hashes -r requirements.lock
COPY . .
RUN useradd --create-home warehouse && mkdir -p /data/photos && chown -R warehouse:warehouse /app /data
USER warehouse
EXPOSE 8010
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8010"]
