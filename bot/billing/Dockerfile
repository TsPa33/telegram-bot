FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY bot/billing/requirements-api.txt /tmp/requirements-api.txt
RUN pip install --no-cache-dir -r /tmp/requirements-api.txt
COPY bot/__init__.py /app/bot/__init__.py
COPY bot/billing /app/bot/billing
RUN rm -rf /app/bot/billing/tests
RUN useradd --uid 10001 --create-home billing
USER billing
CMD ["sh", "-c", "exec uvicorn bot.billing.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
