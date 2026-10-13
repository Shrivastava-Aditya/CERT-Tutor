"""SQLite storage: exam attempts, every answer you give, and (soon) AI-generated questions.

The database file lives in DATA_DIR (/data in Docker, which is /srv/appdata/cert-tutor on the host).
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id          TEXT PRIMARY KEY,
    course      TEXT NOT NULL,
    mode        TEXT NOT NULL,          -- full | half | sprint | drill
    study       INTEGER NOT NULL,       -- 1 = answers revealed as you go
    concept     TEXT,                   -- set for a single-concept drill
    started_at  REAL NOT NULL,
    ends_at     REAL,                   -- NULL = no time limit
    finished_at REAL,
    questions   TEXT NOT NULL,          -- JSON snapshot of the questions, in the order shown
    correct     INTEGER,
    total       INTEGER,
    score       INTEGER
);
CREATE TABLE IF NOT EXISTS answers (
    id          INTEGER PRIMARY KEY,
    attempt_id  TEXT NOT NULL REFERENCES attempts(id),
    course      TEXT NOT NULL,
    question_id TEXT NOT NULL,
    source      TEXT NOT NULL,          -- bank | ai
    pattern     TEXT NOT NULL,
    concept     TEXT NOT NULL,
    domain      TEXT NOT NULL,
    qualifier   TEXT NOT NULL,
    chosen      TEXT NOT NULL,          -- JSON list of option ids
    correct     INTEGER NOT NULL,
    traps       TEXT NOT NULL,          -- JSON list of trap ids you picked
    seconds     REAL,
    flagged     INTEGER NOT NULL DEFAULT 0,
    xp          INTEGER NOT NULL DEFAULT 0,
    answered_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS answers_course ON answers(course, pattern);
"""


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


@contextmanager
def connect():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "tutor.db")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)   # CREATE ... IF NOT EXISTS, so this is safe every time
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------- attempts ----------------

def create_attempt(attempt_id, course, mode, study, concept, questions, minutes):
    now = time.time()
    with connect() as conn:
        conn.execute(
            "INSERT INTO attempts (id, course, mode, study, concept, started_at, ends_at, questions) VALUES (?,?,?,?,?,?,?,?)",
            (attempt_id, course, mode, int(study), concept, now, now + minutes * 60 if minutes else None, json.dumps(questions)),
        )


def get_attempt(attempt_id) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
    if row is None:
        return None
    attempt = dict(row)
    attempt["questions"] = json.loads(attempt["questions"])
    return attempt


def finish_attempt(attempt_id, rows: list[dict], correct: int, total: int, score: int):
    """Store every graded answer and the final score in one transaction."""
    now = time.time()
    with connect() as conn:
        conn.executemany(
            """INSERT INTO answers (attempt_id, course, question_id, source, pattern, concept, domain, qualifier,
                                    chosen, correct, traps, seconds, flagged, xp, answered_at)
               VALUES (:attempt_id, :course, :question_id, :source, :pattern, :concept, :domain, :qualifier,
                       :chosen, :correct, :traps, :seconds, :flagged, :xp, :answered_at)""",
            [{**r, "chosen": json.dumps(r["chosen"]), "traps": json.dumps(r["traps"]), "answered_at": now} for r in rows],
        )
        conn.execute("UPDATE attempts SET finished_at = ?, correct = ?, total = ?, score = ? WHERE id = ?",
                     (now, correct, total, score, attempt_id))


def recent_attempts(course, limit=10) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, mode, study, concept, started_at, correct, total, score FROM attempts "
            "WHERE course = ? AND finished_at IS NOT NULL ORDER BY started_at DESC LIMIT ?", (course, limit)).fetchall()
    return [dict(r) for r in rows]


def missed_patterns(course) -> set[str]:
    """Patterns you've answered wrong at least once; correct answers on these earn bonus XP."""
    with connect() as conn:
        rows = conn.execute("SELECT DISTINCT pattern FROM answers WHERE course = ? AND correct = 0", (course,)).fetchall()
    return {r["pattern"] for r in rows}


def course_answers(course) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM answers WHERE course = ? ORDER BY answered_at", (course,)).fetchall()
    return [{**dict(r), "traps": json.loads(r["traps"]), "chosen": json.loads(r["chosen"])} for r in rows]


# ---------------- XP and streak (shown in the nav bar) ----------------

def player_stats() -> dict:
    with connect() as conn:
        xp = conn.execute("SELECT COALESCE(SUM(xp), 0) FROM answers").fetchone()[0]
        days = {r[0] for r in conn.execute("SELECT DISTINCT date(answered_at, 'unixepoch', 'localtime') FROM answers")}
    # Streak: consecutive days up to today (or up to yesterday, if you haven't studied yet today)
    streak, day = 0, date.today()
    if day.isoformat() not in days:
        day -= timedelta(days=1)
    while day.isoformat() in days:
        streak += 1
        day -= timedelta(days=1)
    return {"xp": xp, "level": 1 + xp // 500, "streak": streak, "studied_today": date.today().isoformat() in days}


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b, %H:%M")
