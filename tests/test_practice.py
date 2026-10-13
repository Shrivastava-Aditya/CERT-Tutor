import json
import random

import pytest
from fastapi.testclient import TestClient

from app import db, questions
from app.content import load_course
from app.main import app
from app.web import CONTENT_DIR

COURSE = "aws-saa-c03"
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test gets its own empty database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def start(**form):
    res = client.post(f"/practice/{COURSE}", data=form, follow_redirects=False)
    assert res.status_code == 303
    return res.headers["location"].rsplit("/", 1)[-1]


def right_answers(attempt):
    return {q["id"]: [o["id"] for o in q["options"] if o["correct"]] for q in attempt["questions"]}


def test_exam_page_hides_answers():
    attempt_id = start(mode="sprint")
    page = client.get(f"/attempt/{attempt_id}")
    assert page.status_code == 200
    config = page.text.split('id="exam-config">', 1)[1].split("</script>", 1)[0]
    assert '"correct"' not in config and "trap_why" not in config
    assert len(json.loads(config)["questions"]) == 10


def test_perfect_submission_scores_1000_and_earns_xp():
    attempt_id = start(mode="sprint")
    attempt = db.get_attempt(attempt_id)
    res = client.post(f"/attempt/{attempt_id}/submit", json={"answers": right_answers(attempt)})
    assert res.json()["redirect"].endswith("/results")
    done = db.get_attempt(attempt_id)
    assert (done["correct"], done["total"], done["score"]) == (10, 10, 1000)
    assert db.player_stats()["xp"] == 100
    assert "1000" in client.get(f"/attempt/{attempt_id}/results").text


def test_wrong_answers_show_up_as_traps_in_insights():
    attempt_id = start(mode="sprint")
    attempt = db.get_attempt(attempt_id)
    wrong = {q["id"]: [next(o["id"] for o in q["options"] if not o["correct"])][: q["choose"]] for q in attempt["questions"]}
    client.post(f"/attempt/{attempt_id}/submit", json={"answers": wrong})
    assert db.get_attempt(attempt_id)["score"] == 100
    page = client.get(f"/insights/{COURSE}").text
    assert "Traps you fall for" in page and "×1" in page


def test_submitting_twice_doesnt_double_count():
    attempt_id = start(mode="sprint")
    answers = right_answers(db.get_attempt(attempt_id))
    client.post(f"/attempt/{attempt_id}/submit", json={"answers": answers})
    client.post(f"/attempt/{attempt_id}/submit", json={"answers": answers})
    assert len([a for a in db.course_answers(COURSE) if a["attempt_id"] == attempt_id]) == 10


def test_concept_drill_is_untimed_study_mode_with_answers():
    attempt_id = start(concept="fsx-windows")
    attempt = db.get_attempt(attempt_id)
    assert attempt["mode"] == "drill" and attempt["study"] == 1 and attempt["ends_at"] is None
    assert all(q["concept"] == "fsx-windows" for q in attempt["questions"])
    assert "trap_why" in client.get(f"/attempt/{attempt_id}").text


def test_pick_follows_domain_weights():
    course = load_course(CONTENT_DIR / COURSE)
    chosen = questions.pick(course, questions.pool(course), 30, rng=random.Random(1))
    counts = {d: sum(q["domain"] == d for q in chosen) for d in ("secure", "resilient", "performance", "cost")}
    assert sum(counts.values()) == 30
    assert counts["secure"] == 9 and counts["cost"] == 6   # 30% and 20% of 30


def test_choose_two_needs_both_right():
    q = {"options": [{"id": "o0", "correct": True}, {"id": "o1", "correct": True}, {"id": "o2", "correct": False, "trap": "t"}]}
    assert questions.grade(q, ["o0", "o1"]) == (True, [])
    assert questions.grade(q, ["o0", "o2"]) == (False, ["t"])
    assert questions.grade(q, ["o0"])[0] is False


def test_insights_log_modules_and_time():
    attempt_id = start(mode="sprint")
    attempt = db.get_attempt(attempt_id)
    first = attempt["questions"][0]
    wrong = {first["id"]: [next(o["id"] for o in first["options"] if not o["correct"])][: first["choose"]]}
    answers = {**right_answers(attempt), **wrong}
    seconds = {q["id"]: 30 + 20 * i for i, q in enumerate(attempt["questions"])}
    client.post(f"/attempt/{attempt_id}/submit", json={"answers": answers, "seconds": seconds})

    page = client.get(f"/insights/{COURSE}").text
    for tab in ("By module", "Every answer", "Time"):
        assert tab in page
    assert first["stem"][:60] in page                     # the wrong question is listed under its module
    assert page.count('data-result="wrong"') == 1 and page.count('data-result="right"') == 9
    assert "210s" in page                                   # the slowest answer (30 + 20*9) shows its time
