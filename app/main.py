"""Cert Tutor web app."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.icons import icon_url
from app.tracks import load_tracks

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR.parent / "content"

app = FastAPI(title="Cert Tutor")

# /static/... serves CSS, JS and images straight from app/static/
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Jinja2 fills HTML templates in app/templates/ with Python values
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["icon_url"] = icon_url


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Read the YAML on every request, so edits to tracks.yaml show up on refresh
    tracks = load_tracks(CONTENT_DIR / "tracks.yaml")
    # Home shows only the tracks you're studying; /tracks shows everything
    shown = [t for t in tracks["tracks"] if t["studying"]]
    return templates.TemplateResponse(request, "home.html", {"title": "Cert Tutor", "map": tracks, "shown": shown, "page": "home"})


@app.get("/tracks", response_class=HTMLResponse)
def tracks_page(request: Request):
    tracks = load_tracks(CONTENT_DIR / "tracks.yaml")
    return templates.TemplateResponse(request, "tracks.html", {"title": "Tracks · Cert Tutor", "map": tracks, "page": "tracks"})


@app.get("/health")
def health():
    """Docker and you can call this to check the app is alive."""
    return {"status": "ok"}
