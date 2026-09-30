FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && useradd --uid 10001 --create-home docmind
COPY --chown=docmind:docmind app ./app
COPY --chown=docmind:docmind alembic ./alembic
COPY --chown=docmind:docmind alembic.ini .
USER docmind
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
