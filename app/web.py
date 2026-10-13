"""Things every page needs: templates, filters, course loading."""
import re
from pathlib import Path

import markdown
import yaml
from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import db
from app.content import load_course, validate
from app.icons import icon_url

BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR.parent / "content"
COURSE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")   # folder names only, so "../" can't escape content/

# Jinja2 fills HTML templates in app/templates/ with Python values
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def asset(path: str) -> str:
    """/static URL with the file's modification time attached, so browsers fetch changed files instead of a cached copy."""
    file = BASE_DIR / "static" / path
    version = int(file.stat().st_mtime) if file.is_file() else 0
    return f"/static/{path}?v={version}"


def highlight(text: str, clues: list[str]) -> Markup:
    """Escape text, then wrap each clue phrase in <mark> so it lights up in the review."""
    html = str(escape(text))
    for clue in sorted(clues or [], key=len, reverse=True):
        pattern = re.compile(re.escape(str(escape(clue))), re.IGNORECASE)
        html = pattern.sub(lambda m: f'<mark class="clue-hit">{m.group(0)}</mark>', html, count=1)
    return Markup(html)


def active_course() -> str | None:
    """The course you're studying now (status: active in tracks.yaml), for the nav links."""
    data = yaml.safe_load((CONTENT_DIR / "tracks.yaml").read_text())
    for track in data["tracks"]:
        for lane in track["lanes"]:
            for c in lane["certs"]:
                if c.get("status") == "active" and c.get("content"):
                    return c["content"]
    return None


templates.env.globals["active_course"] = active_course
templates.env.globals["icon_url"] = icon_url
templates.env.globals["asset"] = asset
templates.env.globals["player"] = db.player_stats
templates.env.filters["highlight"] = highlight
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


def course_or_error_page(request: Request, course_id: str):
    """(course, None) when the course is fine, or (None, error page response) when its YAML is broken."""
    course, errors = get_course(course_id)
    if errors:
        return None, render(request, "course_errors.html", {"title": "Course has errors", "course": course, "errors": errors, "page": "tracks"}, 500)
    return course, None


def provider_logo(course) -> str:
    return icon_url(f"{course.cert.get('provider', '')}:logo")
