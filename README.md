# Cert Tutor

A self-hosted tutor for certification exams (AWS SAA-C03 first, then more AWS, CKA/CKAD and others). It teaches each concept, drills the clue-word patterns exam questions are built on, tracks which traps catch you, and schedules spaced review.

## Run

```
./tools/fetch_icons.sh        # once: downloads the official AWS, Azure and Kubernetes icons
docker compose up -d --build
```

The provider icons are not stored in git. AWS, Microsoft and the CNCF allow them in architecture diagrams and training material, so the script downloads them into `app/static/vendor/` on each machine.

Then open http://<homelab-ip>:8090. Health check: `curl localhost:8090/health`.

## Settings (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Turns on the AI question generator |
| `QUESTION_MODEL` | `claude-opus-5-5` | Model that writes questions |
| `GEN_DAILY_LIMIT` | `60` | Most AI questions generated per day (about $0.03 per 2 questions on Opus 5.5; half that for after-attempt batch runs) |
| `TUTOR_MODEL` | `claude-opus-5-5` | Model the tutor chats with |
| `TUTOR_DAILY_LIMIT` | `200` | Most tutor replies per day |
| `HEADROOM_URL` | (none) | Send tutor calls through the Headroom proxy (`docker compose --profile headroom up -d`, then `http://headroom:8787`) |

## Tests

```
docker compose run --rm test                                              # pytest
docker compose run --rm test python tools/validate.py content/aws-saa-c03 # content checks
```

## Layout

| Path | What it holds |
|---|---|
| `app/` | FastAPI app, templates, static files |
| `content/` | Course content as YAML, one folder per certification |
| `reference/` | v1 static practice exam, kept for reuse |
