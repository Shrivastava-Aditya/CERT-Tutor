"""Cert Tutor web app."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import db, insights, learn, practice
from app.tracks import load_tracks
from app.web import BASE_DIR, CONTENT_DIR, course_or_error_page, provider_logo, render

app = FastAPI(title="Cert Tutor")

# /static/... serves CSS, JS and images straight from app/static/
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
# Test simulator, drills, results and insights live in app/practice.py
app.include_router(practice.router)


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
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    analysis = insights.analyse(course, db.course_answers(course_id))
    return render(request, "course.html", {
        "title": f"{course.cert['code']} · Cert Tutor",
        "page": "tracks",
        "course_id": course_id,
        "cert": course.cert,
        "logo": provider_logo(course),
        "domains": learn.domains_with_concepts(course),
        "stats": learn.concept_stats(course),
        "graph": learn.graph(course, course_id, analysis["mastery"]),
        "analysis": analysis,
        "counts": {"concepts": len(course.concepts), "patterns": len(course.patterns), "questions": len(course.questions)},
    })


@app.get("/course/{course_id}/{concept_id}", response_class=HTMLResponse)
def concept_page(request: Request, course_id: str, concept_id: str):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    concept = course.concepts.get(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="No such concept")
    prev_c, next_c = learn.neighbours(course, concept_id)
    domain = next(d for d in course.cert["domains"] if d["id"] == concept["domain"])
    analysis = insights.analyse(course, db.course_answers(course_id))
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
        "question_count": learn.concept_stats(course)[concept_id]["questions"],
        "pattern_scores": {p["id"]: p for p in analysis["patterns"]},
        "graph": learn.graph(course, course_id, analysis["mastery"]),
        "prev": prev_c,
        "next": next_c,
    })


@app.get("/health")
def health():
    """Docker and you can call this to check the app is alive."""
    return {"status": "ok"}
