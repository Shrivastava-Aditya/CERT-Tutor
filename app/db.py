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
CREATE TABLE IF NOT EXISTS generated_questions (
    id          TEXT PRIMARY KEY,
    course      TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    data        TEXT NOT NULL,          -- the question, same shape as a YAML bank question
    status      TEXT NOT NULL,          -- ready | rejected | reported
    problems    TEXT,                   -- why the validator rejected it
    model       TEXT,
    job_id      TEXT,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS gen_jobs (
    id            TEXT PRIMARY KEY,
    course        TEXT NOT NULL,
    reason        TEXT NOT NULL,        -- button | after-attempt
    patterns      TEXT NOT NULL,        -- JSON list of pattern ids
    status        TEXT NOT NULL,        -- running | done | failed
    made          INTEGER NOT NULL DEFAULT 0,
    rejected      INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    started_at    REAL NOT NULL,
    finished_at   REAL,
    is_batch      INTEGER NOT NULL DEFAULT 0,
    batch_id      TEXT
);
CREATE TABLE IF NOT EXISTS tutor_usage (
    id            INTEGER PRIMARY KEY,
    course        TEXT NOT NULL,
    concept       TEXT,
    mode          TEXT NOT NULL,
    model         TEXT NOT NULL,
    via_headroom  INTEGER NOT NULL DEFAULT 0,
    input_tokens  INTEGER NOT NULL,
    cache_read    INTEGER NOT NULL,
    cache_write   INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    created_at    REAL NOT NULL
);
"""

# Columns added after a table first shipped: (table, column, definition). Applied once to older databases.
MIGRATIONS = [
    ("gen_jobs", "is_batch", "INTEGER NOT NULL DEFAULT 0"),
    ("gen_jobs", "batch_id", "TEXT"),
]


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
        for table, column, definition in MIGRATIONS:
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
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


def times_seen(course) -> dict[str, int]:
    """question id -> how many times you've answered it, so exams can prefer questions you haven't seen."""
    with connect() as conn:
        rows = conn.execute("SELECT question_id, COUNT(*) AS n FROM answers WHERE course = ? GROUP BY question_id", (course,)).fetchall()
    return {r["question_id"]: r["n"] for r in rows}


# ---------------- AI-generated questions ----------------

def add_generated(course, pattern, question, status, problems, model, job_id):
    with connect() as conn:
        conn.execute(
            "INSERT INTO generated_questions (id, course, pattern, data, status, problems, model, job_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (question["id"], course, pattern, json.dumps(question), status, json.dumps(problems) if problems else None, model, job_id, time.time()),
        )


def ready_generated(course) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT data FROM generated_questions WHERE course = ? AND status = 'ready'", (course,)).fetchall()
    return [json.loads(r["data"]) for r in rows]


def generated_counts(course) -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM generated_questions WHERE course = ? GROUP BY status", (course,)).fetchall()
        today = conn.execute(
            "SELECT COUNT(*) FROM generated_questions WHERE course = ? AND date(created_at, 'unixepoch', 'localtime') = date('now', 'localtime')",
            (course,)).fetchone()[0]
    counts = {r["status"]: r["n"] for r in rows}
    return {"ready": counts.get("ready", 0), "rejected": counts.get("rejected", 0), "reported": counts.get("reported", 0), "today": today}


def report_question(question_id) -> bool:
    with connect() as conn:
        return conn.execute("UPDATE generated_questions SET status = 'reported' WHERE id = ? AND status = 'ready'", (question_id,)).rowcount > 0


def start_job(job_id, course, reason, patterns, batch=False):
    with connect() as conn:
        conn.execute("INSERT INTO gen_jobs (id, course, reason, patterns, status, started_at, is_batch) VALUES (?,?,?,?, 'running', ?, ?)",
                     (job_id, course, reason, json.dumps(patterns), time.time(), int(batch)))


def get_job(job_id) -> dict:
    with connect() as conn:
        return dict(conn.execute("SELECT * FROM gen_jobs WHERE id = ?", (job_id,)).fetchone())


def waiting_batch_jobs() -> list[dict]:
    """Batch jobs submitted less than a day ago that haven't finished (the Batches API gives up after 24 hours)."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM gen_jobs WHERE status = 'running' AND is_batch = 1 AND batch_id IS NOT NULL AND started_at > ?",
                            (time.time() - 86400,)).fetchall()
    return [dict(r) for r in rows]


def update_job(job_id, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE gen_jobs SET {sets} WHERE id = ?", (*fields.values(), job_id))


def add_job_tokens(job_id, input_tokens, output_tokens, made, rejected):
    with connect() as conn:
        conn.execute("UPDATE gen_jobs SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?, "
                     "made = made + ?, rejected = rejected + ? WHERE id = ?", (input_tokens, output_tokens, made, rejected, job_id))


def running_job(course) -> dict | None:
    """A job still marked running. Instant jobs older than 15 minutes count as dead (the app restarted mid-job);
    batch jobs get 24 hours, the Batches API's own limit."""
    now = time.time()
    with connect() as conn:
        row = conn.execute("SELECT * FROM gen_jobs WHERE course = ? AND status = 'running' AND "
                           "((is_batch = 0 AND started_at > ?) OR (is_batch = 1 AND started_at > ?)) ORDER BY started_at DESC LIMIT 1",
                           (course, now - 900, now - 86400)).fetchone()
    return dict(row) if row else None


def recent_jobs(course, limit=5) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM gen_jobs WHERE course = ? ORDER BY started_at DESC LIMIT ?", (course, limit)).fetchall()
    return [dict(r) for r in rows]


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


def log_tutor_usage(course, concept, mode, model, via_headroom, usage):
    with connect() as conn:
        conn.execute("INSERT INTO tutor_usage (course, concept, mode, model, via_headroom, input_tokens, cache_read, cache_write, output_tokens, created_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (course, concept, mode, model, int(via_headroom), usage.input_tokens, usage.cache_read_input_tokens or 0,
                      usage.cache_creation_input_tokens or 0, usage.output_tokens, time.time()))


def tutor_replies_today(course) -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM tutor_usage WHERE course = ? AND date(created_at, 'unixepoch', 'localtime') = date('now', 'localtime')",
                            (course,)).fetchone()[0]


def tutor_usage_summary(course) -> list[dict]:
    """Average tokens per tutor reply, split by whether Headroom was in the path, so the two can be compared."""
    with connect() as conn:
        rows = conn.execute("SELECT via_headroom, COUNT(*) AS replies, AVG(input_tokens) AS input, AVG(cache_read) AS cache_read, "
                            "AVG(cache_write) AS cache_write, AVG(output_tokens) AS output FROM tutor_usage WHERE course = ? GROUP BY via_headroom",
                            (course,)).fetchall()
    return [dict(r) for r in rows]


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b, %H:%M")
