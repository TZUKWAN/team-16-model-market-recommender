# ---- Shared dependency build stage ----
FROM python:3.11-slim AS base-builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install Python dependencies
COPY requirements.txt requirements-lock.txt ./
RUN pip install --no-cache-dir --user -r requirements-lock.txt

# ---- Optional CPU dense dependency stage ----
FROM base-builder AS dense-builder

COPY requirements-embeddings.in requirements-embeddings.txt requirements-embeddings-lock.txt ./
RUN pip install --no-cache-dir --user -r requirements-embeddings-lock.txt

# ---- Shared runtime stage ----
FROM python:3.11-slim AS runtime-base

WORKDIR /app/backend

# Copy installed packages from builder
COPY --from=base-builder /root/.local /root/.local

# Ensure local bin is in PATH
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY app/ ./app/
COPY requirements.txt requirements-lock.txt ./

# Default environment variables
ENV PYTHONPATH=/app/backend
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://localhost:8000/api/v1/health')); raise SystemExit(0 if data.get('status') == 'healthy' else 1)"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Default lightweight runtime. It never downloads embedding weights implicitly.
FROM runtime-base AS runtime-light

# Competition runtime with pinned CPU embedding dependencies and preparation CLI.
FROM runtime-base AS runtime-dense
COPY --from=dense-builder /root/.local /root/.local
COPY requirements-embeddings.in requirements-embeddings.txt requirements-embeddings-lock.txt ./
COPY scripts/prepare_dense_model.py ./scripts/prepare_dense_model.py

# Keep plain `docker build` lightweight unless a caller selects runtime-dense.
FROM runtime-light AS runtime
