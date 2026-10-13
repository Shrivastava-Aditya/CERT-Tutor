# ---- base: Python + app dependencies, shared by the other stages ----
# Small official Python image (Debian "slim" = fewer extra packages)
FROM python:3.13-slim AS base

# Don't write .pyc files; print logs straight away instead of buffering them
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first, so Docker can reuse this layer when only app code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# A normal user (uid 1000 = your user on the host), so nothing runs as root
RUN useradd --uid 1000 --create-home tutor

# ---- dev: adds pytest; the repo is mounted at /app by the "test" service ----
FROM base AS dev
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
USER tutor
CMD ["python", "-m", "pytest", "-q"]

# ---- prod: what actually runs (last stage = the default) ----
FROM base AS prod
COPY app ./app
USER tutor
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
