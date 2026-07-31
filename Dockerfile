FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/
RUN pip install build && python -m build --wheel

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install /tmp/brompt_engine-*.whl \
    && pip install "fastapi>=0.104.0" "uvicorn[standard]>=0.24.0" "httpx>=0.25.0" "python-multipart>=0.0.6" \
    && rm /tmp/brompt_engine-*.whl

EXPOSE 8000

COPY agent.brompt.yaml /app/agent.brompt.yaml
WORKDIR /app

CMD ["uvicorn", "brompt.api.routes:create_app()", "--host", "0.0.0.0", "--port", "8000"]
