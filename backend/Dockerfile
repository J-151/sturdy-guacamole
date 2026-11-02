# ---- Backend image: Python 3.12 + FastAPI ----------------------------------
# Build context is the REPOSITORY ROOT (see docker-compose.yml), because we need
# requirements.txt (root) and the backend/ package.
FROM python:3.12-slim

# Don't write .pyc files; print logs immediately (so `docker compose logs` is live).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first: Docker caches this layer, so rebuilds are fast
# unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then copy the application code.
COPY backend ./backend

EXPOSE 8000

# Healthy once the API answers. start_period is generous because the first start downloads data.
HEALTHCHECK --interval=15s --timeout=5s --start-period=240s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "-m", "backend.scripts.start"]
