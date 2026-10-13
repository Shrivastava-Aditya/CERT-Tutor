"""Cert Tutor web app.

Loop 1: the skeleton. One page and one health check, served by FastAPI.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent

app = FastAPI(title="Cert Tutor")

# /static/... serves CSS, JS and images straight from app/static/
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Jinja2 fills HTML templates in app/templates/ with Python values
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"title": "Cert Tutor"})


@app.get("/health")
def health():
    """Docker and you can call this to check the app is alive."""
    return {"status": "ok"}
