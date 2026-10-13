"""Cert Tutor web app."""
import re
from pathlib import Path

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app import learn
from app.content import load_course, validate
from app.icons import icon_url
from app.tracks import load_tracks

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR.parent / "content"
COURSE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")   # folder names only, so "../" can't escape content/

app = FastAPI(title="Cert Tutor")

# /static/... serves CSS, JS and images straight from app/static/
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Jinja2 fills HTML templates in app/templates/ with Python values
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["icon_url"] = icon_url


def asset(path: str) -> str:
    """/static URL with the file's modification time attached, so browsers fetch changed files instead of a cached copy."""
    file = BASE_DIR / "static" / path
    version = int(file.stat().st_mtime) if file.is_file() else 0
    return f"/static/{path}?v={version}"


templates.env.globals["asset"] = asset
# Course text is written in Markdown (tables, bold, `code`); our own YAML, so it's trusted HTML
templates.env.filters["md"] = lambda text: Markup(markdown.markdown(text or "", extensions=["tables", "sane_lists"]))


def render(request: Request, name: str, context: dict, status_code: int = 200):
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def get_course(course_id: str):
    """Load a course by folder name. 404 if it doesn't exist; returns (course, errors)."""
    if not COURSE_ID.match(course_id) or not (CONTENT_DIR / course_id / "cert.yaml").is_file():
        raise HTTPException(status_code=404, detail="No such course")
    course = load_course(CONTENT_DIR / course_id)
    errors = [i for i in validate(course) if i.level == "error"]
    return course, errors


def provider_logo(course) -> str:
    return icon_url(f"{course.cert.get('provider', '')}:logo")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Read the YAML on every request, so edits show up on refresh
    tracks = load_tracks(CONTENT_DIR / "tracks.yaml")
    # Home shows only the tracks you're studying; /tracks shows everything
    shown = [t for t in tracks["tracks"] if t["studying"]]
    return render(request, "home.html", {"title": "Cert Tutor", "map": tracks, "shown": shown, "page": "home"})


@app.get("/tracks", response_class=HTMLResponse)
def tracks_page(request: Request):
    tracks = load_tracks(CONTENT_DIR / "tracks.yaml")
    return render(request, "tracks.html", {"title": "Tracks · Cert Tutor", "map": tracks, "page": "tracks"})


@app.get("/course/{course_id}", response_class=HTMLResponse)
def course_page(request: Request, course_id: str):
    course, errors = get_course(course_id)
    if errors:
        return render(request, "course_errors.html", {"title": "Course has errors", "course": course, "errors": errors, "page": "tracks"}, 500)
    return render(request, "course.html", {
        "title": f"{course.cert['code']} · Cert Tutor",
        "page": "tracks",
        "course_id": course_id,
        "cert": course.cert,
        "logo": provider_logo(course),
        "domains": learn.domains_with_concepts(course),
        "stats": learn.concept_stats(course),
        "graph": learn.graph(course, course_id),
        "counts": {"concepts": len(course.concepts), "patterns": len(course.patterns), "questions": len(course.questions)},
    })


@app.get("/course/{course_id}/{concept_id}", response_class=HTMLResponse)
def concept_page(request: Request, course_id: str, concept_id: str):
    course, errors = get_course(course_id)
    if errors:
        return render(request, "course_errors.html", {"title": "Course has errors", "course": course, "errors": errors, "page": "tracks"}, 500)
    concept = course.concepts.get(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="No such concept")
    prev_c, next_c = learn.neighbours(course, concept_id)
    domain = next(d for d in course.cert["domains"] if d["id"] == concept["domain"])
    return render(request, "concept.html", {
        "title": f"{concept['title']} · {course.cert['code']}",
        "page": "tracks",
        "course_id": course_id,
        "cert": course.cert,
        "concept": concept,
        "domain": domain,
        "tabs": [t for t in learn.TABS if concept.get(t[0])],
        "cloud_names": learn.CLOUD_NAMES,
        "patterns": learn.concept_stats(course)[concept_id]["patterns"],
        "related": [(rel, course.concepts.get(rel)) for rel in concept.get("related", [])],
        "graph": learn.graph(course, course_id),
        "prev": prev_c,
        "next": next_c,
    })


@app.get("/health")
def health():
    """Docker and you can call this to check the app is alive."""
    return {"status": "ok"}
