"""Test simulator and drills: start an attempt, take it, submit it, see results and insights."""
import secrets
import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import db, insights, questions
from app.web import course_or_error_page, provider_logo, render

router = APIRouter()
GRACE_SECONDS = 30   # accept a submission slightly after the timer ends (slow network, tab asleep)


@router.get("/practice/{course_id}", response_class=HTMLResponse)
def practice_home(request: Request, course_id: str):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    analysis = insights.analyse(course, db.course_answers(course_id))
    return render(request, "practice.html", {
        "title": f"Practice · {course.cert['code']}",
        "page": "practice",
        "course_id": course_id,
        "cert": course.cert,
        "logo": provider_logo(course),
        "modes": questions.MODES,
        "pool_size": len(questions.pool(course)),
        "attempts": db.recent_attempts(course_id),
        "analysis": analysis,
        "fmt_time": db.fmt_time,
    })


@router.post("/practice/{course_id}")
def start_attempt(request: Request, course_id: str, mode: str = Form("full"), study: bool = Form(False),
                  concept: str = Form("")):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    if concept:
        if concept not in course.concepts:
            raise HTTPException(status_code=404, detail="No such concept")
        chosen = questions.pool(course, concept)
        mode, minutes, study = "drill", None, True       # a concept drill: untimed, answers shown as you go
    else:
        if mode not in questions.MODES:
            raise HTTPException(status_code=400, detail="Unknown mode")
        n, minutes, _ = questions.MODES[mode]
        chosen = questions.pick(course, questions.pool(course), n)
    attempt_id = secrets.token_urlsafe(8)
    db.create_attempt(attempt_id, course_id, mode, study, concept or None, questions.shuffled(chosen), minutes)
    # 303 = "see other": the browser follows with a GET, so refreshing doesn't start another attempt
    return RedirectResponse(f"/attempt/{attempt_id}", status_code=303)


def load_attempt(attempt_id: str) -> dict:
    attempt = db.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="No such attempt")
    return attempt


@router.get("/attempt/{attempt_id}", response_class=HTMLResponse)
def take_attempt(request: Request, attempt_id: str):
    attempt = load_attempt(attempt_id)
    if attempt["finished_at"]:
        return RedirectResponse(f"/attempt/{attempt_id}/results", status_code=303)
    course, error = course_or_error_page(request, attempt["course"])
    if error:
        return error
    label = "Drill: " + course.concepts[attempt["concept"]]["title"] if attempt["concept"] else questions.MODES[attempt["mode"]][2]
    return render(request, "attempt.html", {
        "title": f"{label} · {course.cert['code']}",
        "page": "practice",
        "label": label,
        "cert": course.cert,
        "config": {
            "id": attempt_id,
            "course": attempt["course"],
            "study": bool(attempt["study"]),
            "endsAt": attempt["ends_at"],
            "serverNow": time.time(),
            "questions": [questions.public(q, bool(attempt["study"])) for q in attempt["questions"]],
        },
    })


class Submission(BaseModel):
    answers: dict[str, list[str]] = {}
    flags: dict[str, bool] = {}
    seconds: dict[str, float] = {}


@router.post("/attempt/{attempt_id}/submit")
def submit_attempt(attempt_id: str, sub: Submission):
    attempt = load_attempt(attempt_id)
    done = {"redirect": f"/attempt/{attempt_id}/results"}
    if attempt["finished_at"]:
        return done                     # already submitted (double click, retry): nothing to do
    if attempt["ends_at"] and time.time() > attempt["ends_at"] + GRACE_SECONDS:
        sub.answers = {}                # far past the deadline: answers no longer count
    missed_before = db.missed_patterns(attempt["course"])
    rows, correct = [], 0
    for q in attempt["questions"]:
        chosen = sub.answers.get(q["id"], [])
        ok, traps = questions.grade(q, chosen)
        correct += ok
        xp = (questions.XP_CORRECT + (questions.XP_COMEBACK if q["pattern"] in missed_before else 0)) if ok else 0
        rows.append({
            "attempt_id": attempt_id, "course": attempt["course"], "question_id": q["id"], "source": q["source"],
            "pattern": q["pattern"], "concept": q["concept"], "domain": q["domain"], "qualifier": q["qualifier"],
            "chosen": chosen, "correct": int(ok), "traps": traps,
            "seconds": sub.seconds.get(q["id"]), "flagged": int(sub.flags.get(q["id"], False)), "xp": xp,
        })
    total = len(attempt["questions"])
    db.finish_attempt(attempt_id, rows, correct, total, questions.scaled_score(correct, total))
    return JSONResponse(done)


@router.get("/attempt/{attempt_id}/results", response_class=HTMLResponse)
def attempt_results(request: Request, attempt_id: str):
    attempt = load_attempt(attempt_id)
    if not attempt["finished_at"]:
        return RedirectResponse(f"/attempt/{attempt_id}", status_code=303)
    course, error = course_or_error_page(request, attempt["course"])
    if error:
        return error
    answers = [a for a in db.course_answers(attempt["course"]) if a["attempt_id"] == attempt_id]
    by_question = {a["question_id"]: a for a in answers}
    review = []
    for n, q in enumerate(attempt["questions"], start=1):
        a = by_question.get(q["id"], {})
        chosen = set(a["chosen"]) if a else set()
        review.append({**q, "n": n, "chosen": chosen, "ok": bool(a.get("correct")), "flagged": bool(a.get("flagged")),
                       "seconds": a.get("seconds")})
    analysis = insights.analyse(course, answers)
    label = "Drill: " + course.concepts[attempt["concept"]]["title"] if attempt["concept"] else questions.MODES[attempt["mode"]][2]
    return render(request, "results.html", {
        "title": f"Results · {course.cert['code']}",
        "page": "practice",
        "course_id": attempt["course"],
        "cert": course.cert,
        "attempt": attempt,
        "label": label,
        "review": review,
        "analysis": analysis,
        "xp": sum(a["xp"] for a in answers),
        "used": min((attempt["finished_at"] - attempt["started_at"]), (attempt["ends_at"] or 1e18) - attempt["started_at"]),
        "passing": course.cert["exam"]["passing_score"],
    })


@router.get("/insights/{course_id}", response_class=HTMLResponse)
def insights_page(request: Request, course_id: str):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    return render(request, "insights.html", {
        "title": f"Insights · {course.cert['code']}",
        "page": "insights",
        "course_id": course_id,
        "cert": course.cert,
        "analysis": insights.analyse(course, db.course_answers(course_id)),
        "attempts": db.recent_attempts(course_id, 20),
        "fmt_time": db.fmt_time,
        "passing": course.cert["exam"]["passing_score"],
    })
