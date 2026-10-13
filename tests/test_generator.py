"""The AI generator with Claude mocked out: no network calls, no cost."""
import random
from types import SimpleNamespace

import pytest

from app import db, generator, questions
from app.content import load_course
from app.web import CONTENT_DIR

COURSE = "aws-saa-c03"


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture
def course():
    return load_course(CONTENT_DIR / COURSE)


GOOD = {
    "stem": "A law firm wants to move its Windows file shares to AWS. Staff use SMB, and permissions come from Active Directory.",
    "clues": ["Windows", "SMB", "Active Directory"],
    "qualifier": "least-changes",
    "options": [
        {"text": "Amazon FSx for Windows File Server joined to the firm's AD", "correct": True, "trap": ""},
        {"text": "Amazon EFS mounted on each desktop", "correct": False, "trap": "efs-for-windows"},
        {"text": "An S3 File Gateway", "correct": False, "trap": "s3-file-gateway-as-ha-share"},
        {"text": "EBS Multi-Attach shared by two instances", "correct": False, "trap": "ebs-multi-attach-as-share"},
    ],
    "explain": "FSx for Windows speaks SMB and joins AD; the others don't fit.",
}
BAD = {**GOOD, "clues": ["NFS"], "options": [*GOOD["options"][:3], {"text": "Something else", "correct": False, "trap": ""}]}
USAGE = SimpleNamespace(input_tokens=1000, output_tokens=800, cache_read_input_tokens=0, cache_creation_input_tokens=0)


def test_valid_questions_join_the_pool_and_bad_ones_are_rejected(course, monkeypatch):
    monkeypatch.setattr(generator, "ask_claude", lambda *a, **k: ([GOOD, BAD], USAGE))
    job_id = generator.start(course, COURSE, "button", ["fsx-windows-share"])
    generator.run(course, COURSE, job_id)

    counts = db.generated_counts(COURSE)
    assert (counts["ready"], counts["rejected"]) == (1, 1)
    job = db.recent_jobs(COURSE)[0]
    assert (job["status"], job["made"], job["rejected"], job["output_tokens"]) == ("done", 1, 1, 800)

    pool = questions.pool(course, "fsx-windows", db.ready_generated(COURSE))
    ai = [q for q in pool if q["source"] == "ai"]
    assert len(ai) == 1 and ai[0]["options"][1]["trap_why"]   # enriched with the trap explanation


def test_reported_questions_leave_the_pool(course, monkeypatch):
    monkeypatch.setattr(generator, "ask_claude", lambda *a, **k: ([GOOD], USAGE))
    generator.run(course, COURSE, generator.start(course, COURSE, "button", ["fsx-windows-share"]))
    qid = db.ready_generated(COURSE)[0]["id"]
    assert db.report_question(qid)
    assert db.ready_generated(COURSE) == []


def test_api_failure_marks_the_job_failed(course, monkeypatch):
    def boom(*a, **k):
        raise generator.GenerationError("rate limited")
    monkeypatch.setattr(generator, "ask_claude", boom)
    job_id = generator.start(course, COURSE, "button", ["fsx-windows-share"])
    generator.run(course, COURSE, job_id)
    job = db.recent_jobs(COURSE)[0]
    assert job["status"] == "failed" and "rate limited" in job["error"]


def test_no_key_means_no_job(course, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert generator.start(course, COURSE, "button") is None


def test_plan_favours_weak_patterns(course):
    answers = [{"pattern": "fsx-windows-share", "correct": 0, "traps": ["efs-for-windows"], "domain": "resilient",
                "qualifier": "none", "concept": "fsx-windows", "seconds": 30}] * 3
    hits = sum("fsx-windows-share" in generator.plan(course, answers, [], k=6, rng=random.Random(i)) for i in range(30))
    assert hits == 30            # weak patterns are always in the plan
    assert generator.traps_you_fall_for(answers, "fsx-windows-share") == ["efs-for-windows"]


def test_schema_only_allows_the_patterns_traps(course):
    schema = generator.output_schema(course, course.patterns["fsx-windows-share"])
    trap_enum = schema["properties"]["questions"]["items"]["properties"]["options"]["items"]["properties"]["trap"]["enum"]
    assert trap_enum == ["", "efs-for-windows", "s3-file-gateway-as-ha-share", "ebs-multi-attach-as-share", "fsx-lustre-for-windows"]


class FakeBatchClient:
    """Stands in for anthropic.Anthropic(): accepts a batch, reports it 'in_progress' once, then 'ended' with results."""
    def __init__(self, raws_by_pattern):
        self.raws = raws_by_pattern
        self.polls = 0
        outer = self

        class Batches:
            def create(self, requests):
                outer.submitted = [r["custom_id"] for r in requests]
                return SimpleNamespace(id="msgbatch_test")

            def retrieve(self, batch_id):
                outer.polls += 1
                return SimpleNamespace(processing_status="ended" if outer.polls > 1 else "in_progress")

            def results(self, batch_id):
                import json
                for pid in outer.submitted:
                    message = SimpleNamespace(stop_reason="end_turn", usage=USAGE,
                                              content=[SimpleNamespace(type="text", text=json.dumps({"questions": outer.raws[pid]}))])
                    yield SimpleNamespace(custom_id=pid, result=SimpleNamespace(type="succeeded", message=message))

        self.messages = SimpleNamespace(batches=Batches())


def test_batch_job_submits_waits_and_stores(course, monkeypatch):
    fake = FakeBatchClient({"fsx-windows-share": [GOOD, BAD]})
    monkeypatch.setattr(generator.anthropic, "Anthropic", lambda: fake)
    monkeypatch.setattr(generator, "BATCH_POLL_SECONDS", 0)
    job_id = generator.start(course, COURSE, "after-attempt", ["fsx-windows-share"], batch=True)
    generator.submit_batch(course, COURSE, job_id)

    job = db.get_job(job_id)
    assert fake.submitted == ["fsx-windows-share"] and fake.polls == 2
    assert (job["status"], job["batch_id"], job["is_batch"], job["made"], job["rejected"]) == ("done", "msgbatch_test", 1, 1, 1)
    assert generator.estimate_cost(1000, 800, "claude-opus-5-5", batch=True) == generator.estimate_cost(1000, 800, "claude-opus-5-5") / 2
