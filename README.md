# Cert Tutor

A self-hosted tutor for certification exams (AWS SAA-C03 first, then more AWS, CKA/CKAD and others). It teaches each concept, drills the clue-word patterns exam questions are built on, tracks which traps catch you, and schedules spaced review.

## Run

```
docker compose up -d --build
```

Then open http://<homelab-ip>:8090. Health check: `curl localhost:8090/health`.

## Layout

| Path | What it holds |
|---|---|
| `app/` | FastAPI app, templates, static files |
| `content/` | Course content as YAML, one folder per certification |
| `reference/` | v1 static practice exam, kept for reuse |
