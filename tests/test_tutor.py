"""Tutor prompt building and the chat endpoint, with Claude mocked out."""
import pytest
from fastapi.testclient import TestClient

from app import db, tutor
from app.content import load_course
from app.main import app
from app.web import CONTENT_DIR

COURSE = "aws-saa-c03"
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_history_is_trimmed_and_starts_with_the_learner():
    history = [{"role": "assistant", "content": "hi"}] + [{"role": "user", "content": f"q{i}"} for i in range(30)]
    msgs = tutor.build_messages(history, "explain", "profile text", "")
    assert len(msgs) == tutor.MAX_TURNS and msgs[0]["role"] == "user"
    assert "profile text" in msgs[0]["content"] and msgs[0]["content"].endswith("q10")


def test_concept_card_is_the_cached_prefix():
    course = load_course(CONTENT_DIR / COURSE)
    blocks = tutor.system_blocks(course, course.concepts["efs"])
    assert "cache_control" in blocks[-1] and "Amazon EFS" in blocks[-1]["text"]
    assert all("cache_control" not in b for b in blocks[:-1])


def test_question_context_marks_choice_correct_answer_and_trap():
    q = {"stem": "S", "rule": "R", "clues": ["c"], "options": [
        {"id": "o0", "text": "Right", "correct": True},
        {"id": "o1", "text": "Wrong", "correct": False, "trap_why": "too slow"}]}
    text = tutor.question_context(q, ["o1"])
    assert "Right  [correct answer]" in text and "learner's choice, trap: too slow" in text


def test_chat_endpoint_streams_the_reply(monkeypatch):
    def fake_stream(course, concept, mode, history, context=""):
        assert concept["id"] == "efs" and mode == "quiz"
        yield "Hello "
        yield "learner"
    monkeypatch.setattr(tutor, "stream_reply", fake_stream)
    res = client.post(f"/tutor/{COURSE}/chat", json={"messages": [{"role": "user", "content": "hi"}], "mode": "quiz", "concept": "efs"})
    assert res.status_code == 200 and res.text == "Hello learner"


def test_missing_key_comes_back_as_a_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = client.post(f"/tutor/{COURSE}/chat", json={"messages": [{"role": "user", "content": "hi"}], "concept": "efs"})
    assert "ANTHROPIC_API_KEY" in res.text
