# Cert Tutor

A self-hosted tutor for certification exams (AWS SAA-C03 first, then more AWS, CKA/CKAD and others). It teaches each concept, drills the clue-word patterns exam questions are built on, tracks which traps catch you, and schedules spaced review.

## Run

```
./tools/fetch_icons.sh        # once: downloads the official AWS, Azure and Kubernetes icons
docker compose up -d --build
```

The provider icons are not stored in git. AWS, Microsoft and the CNCF allow them in architecture diagrams and training material, so the script downloads them into `app/static/vendor/` on each machine.

Then open http://<homelab-ip>:8090. Health check: `curl localhost:8090/health`.

## Layout

| Path | What it holds |
|---|---|
| `app/` | FastAPI app, templates, static files |
| `content/` | Course content as YAML, one folder per certification |
| `reference/` | v1 static practice exam, kept for reuse |
