from pathlib import Path

import yaml

from app.content import load_course, validate

REPO = Path(__file__).resolve().parent.parent


def errors(issues):
    return [i.message for i in issues if i.level == "error"]


def test_saa_course_has_no_errors():
    course = load_course(REPO / "content" / "aws-saa-c03")
    assert course.concepts and course.patterns and course.questions
    assert errors(validate(course)) == []


def write_course(root: Path, concepts, patterns, questions):
    (root / "concepts").mkdir(parents=True)
    (root / "patterns").mkdir()
    (root / "questions").mkdir()
    (root / "cert.yaml").write_text(yaml.safe_dump({
        "code": "TEST", "domains": [{"id": "cost"}], "qualifiers": ["none"],
    }))
    for c in concepts:
        (root / "concepts" / f"{c['id']}.yaml").write_text(yaml.safe_dump(c))
    (root / "patterns" / "p.yaml").write_text(yaml.safe_dump(patterns))
    (root / "questions" / "q.yaml").write_text(yaml.safe_dump(questions))


CONCEPT = {
    "id": "s3", "domain": "cost", "title": "S3", "summary": "s", "teach": "t", "under_the_hood": "u",
    "other_clouds": {"azure": "Blob", "gcp": "GCS"}, "links": [{"url": "https://docs.aws.amazon.com/s3"}],
}
PATTERN = {
    "id": "p1", "concept": "s3", "clues": ["cheap"], "rule": "cheap -> IA",
    "traps": [{"id": "t1", "why": "too slow"}],
}


def test_catches_broken_questions(tmp_path):
    questions = [
        {   # clue missing from stem, wrong option with no trap, choose mismatch
            "id": "q1", "pattern": "p1", "stem": "Which storage is fastest?", "clues": ["cheap"],
            "choose": 2, "explain": "e",
            "options": [{"text": "A", "correct": True}, {"text": "B"}, {"text": "C", "trap": "t1"}],
        },
        {   # unknown pattern
            "id": "q2", "pattern": "nope", "stem": "x", "clues": ["x"], "explain": "e",
            "options": [{"text": "A", "correct": True}],
        },
        {   # trap that belongs to no pattern
            "id": "q3", "pattern": "p1", "stem": "cheap storage?", "clues": ["cheap"], "explain": "e",
            "options": [{"text": "A", "correct": True}, {"text": "B", "trap": "t-other"}, {"text": "C", "trap": "t1"}],
        },
    ]
    write_course(tmp_path, [CONCEPT], [PATTERN], questions)
    found = errors(validate(load_course(tmp_path)))

    assert any("clue 'cheap' doesn't appear" in m for m in found)
    assert any("wrong option 2 has no trap" in m for m in found)
    assert any("choose is 2 but 1 option(s)" in m for m in found)
    assert any("pattern 'nope' doesn't exist" in m for m in found)
    assert any("trap 't-other'" in m for m in found)


def test_catches_duplicate_ids_and_bad_concept_links(tmp_path):
    second = dict(PATTERN)   # same id as PATTERN, and points at a missing concept
    second["concept"] = "ghost"
    write_course(tmp_path, [CONCEPT], [PATTERN, second], [])
    found = errors(validate(load_course(tmp_path)))
    assert any("duplicate pattern id 'p1'" in m for m in found)
