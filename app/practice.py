"""Test simulator and drills: start an attempt, take it, submit it, see results and insights."""
import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import db, generator, insights, questions
from app.web import course_or_error_page, get_course, provider_logo, render

router = APIRouter()
GRACE_SECONDS = 30   # accept a submission slightly after the timer ends (slow network, tab asleep)


@router.get("/practice/{course_id}", response_class=HTMLResponse)
def practice_home(request: Request, course_id: str):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    analysis = insights.analyse(course, db.course_answers(course_id))
    jobs = db.recent_jobs(course_id)
    for j in jobs:
        j["cost"] = generator.estimate_cost(j["input_tokens"], j["output_tokens"], batch=bool(j["is_batch"]))
    ai = {
        "available": generator.available(),
        "model": generator.MODEL,
        "counts": db.generated_counts(course_id),
        "running": db.running_job(course_id),
        "jobs": jobs,
        "daily_limit": generator.DAILY_LIMIT,
    }
    return render(request, "practice.html", {
        "ai": ai,
        "title": f"Practice · {course.cert['code']}",
        "page": "practice",
        "course_id": course_id,
        "cert": course.cert,
        "logo": provider_logo(course),
        "modes": questions.MODES,
        "pool_size": len(questions.pool(course, generated=db.ready_generated(course_id))),
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
    generated = db.ready_generated(course_id)
    seen = db.times_seen(course_id)
    if concept:
        if concept not in course.concepts:
            raise HTTPException(status_code=404, detail="No such concept")
        # A concept drill: untimed, answers shown as you go, freshest 10 questions first
        candidates = questions.pool(course, concept, generated)
        chosen = sorted(candidates, key=lambda q: (seen.get(q["id"], 0), secrets.randbelow(1000)))[:10]
        mode, minutes, study = "drill", None, True
    else:
        if mode not in questions.MODES:
            raise HTTPException(status_code=400, detail="Unknown mode")
        n, minutes, _ = questions.MODES[mode]
        chosen = questions.pick(course, questions.pool(course, generated=generated), n, seen=seen)
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
def submit_attempt(attempt_id: str, sub: Submission, background: BackgroundTasks):
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
    # Close the loop: write fresh questions for the patterns you just missed, in the background
    missed = list(dict.fromkeys(r["pattern"] for r in rows if not r["correct"]))[: generator.PATTERNS_PER_JOB]
    if missed:
        # Not urgent, so it goes through the Batches API at half price
        queue_generation(background, attempt["course"], "after-attempt", missed, batch=True)
    return JSONResponse(done)


def queue_generation(background: BackgroundTasks, course_id: str, reason: str, patterns: list[str] | None = None,
                     batch: bool = False) -> str | None:
    course, errors = get_course(course_id)
    if errors:
        return None
    job_id = generator.start(course, course_id, reason, patterns, batch=batch)
    if job_id and batch:
        generator.run_in_thread(generator.submit_batch, course, course_id, job_id)
    elif job_id:
        background.add_task(generator.run, course, course_id, job_id)
    return job_id


@router.post("/practice/{course_id}/generate")
def generate_now(request: Request, course_id: str, background: BackgroundTasks):
    course, error = course_or_error_page(request, course_id)
    if error:
        return error
    queue_generation(background, course_id, "button")
    return RedirectResponse(f"/practice/{course_id}#ai", status_code=303)


@router.get("/practice/{course_id}/gen-status")
def generation_status(course_id: str):
    job = db.running_job(course_id)
    return {"running": bool(job), "made": job["made"] if job else 0, "rejected": job["rejected"] if job else 0,
            "ready": db.generated_counts(course_id)["ready"]}


@router.post("/question/{question_id}/report")
def report_question(question_id: str, back: str = Form("/")):
    db.report_question(question_id)
    # Only redirect within this site
    return RedirectResponse(back if back.startswith("/") and not back.startswith("//") else "/", status_code=303)


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
    answers = db.course_answers(course_id)
    log = insights.answer_log(course, answers, db.attempt_questions(course_id))
    return render(request, "insights.html", {
        "log": log,
        "modules": insights.by_module(course, log),
        "timing": insights.time_stats(log),
        "title": f"Insights · {course.cert['code']}",
        "page": "insights",
        "course_id": course_id,
        "cert": course.cert,
        "analysis": insights.analyse(course, answers),
        "attempts": db.recent_attempts(course_id, 20),
        "tutor_usage": db.tutor_usage_summary(course_id),
        "fmt_time": db.fmt_time,
        "passing": course.cert["exam"]["passing_score"],
    })
