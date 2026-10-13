# Small official Python image (Debian "slim" = fewer extra packages)
FROM python:3.13-slim

# Don't write .pyc files; print logs straight away instead of buffering them
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first, so Docker can reuse this layer when only app code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a normal user (uid 1000 = your user on the host), not root
RUN useradd --uid 1000 --create-home tutor
USER tutor

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
