"""AI question generator: fresh exam questions from each pattern, aimed at your weak spots.

Flow for one job:
  1. plan()      pick patterns, weighting weak and unseen ones more heavily
  2. ask Claude  one request per pattern, answer forced into a JSON schema
                 (trap ids are an enum, so a wrong option can only name a real trap)
  3. validate    the same question_problems() rules the YAML bank passes
  4. store       valid questions become 'ready' and join the exam pool; the rest are kept as 'rejected' with reasons
"""
import json
import os
import random
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import anthropic

from app import db, insights
from app.content import Course, question_problems

MODEL = os.environ.get("QUESTION_MODEL", "claude-opus-5-5")
PER_PATTERN = 2                                         # questions per pattern per job
PATTERNS_PER_JOB = 6
DAILY_LIMIT = int(os.environ.get("GEN_DAILY_LIMIT", "60"))   # cap on generated questions per day
# Models that accept the server-side refusal fallback (see the Claude API docs)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
PRICES = {  # $ per million tokens (input, output), for the cost estimate on the practice page
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
}


class GenerationError(Exception):
    pass


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def estimate_cost(input_tokens: int, output_tokens: int, model: str = MODEL) -> float:
    price_in, price_out = PRICES.get(model, (4.0, 20.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


# ---------------- 1. which patterns to generate for ----------------

def plan(course: Course, answers: list[dict], ready: list[dict], k: int = PATTERNS_PER_JOB, rng=random) -> list[str]:
    """Weak patterns always come first (worst score first, then those with the fewest unused AI questions).
    Any slots left go to a weighted draw that favours patterns you haven't been tested on yet,
    and one slot is kept for that discovery whenever there's anything else to discover."""
    scores = {p["id"]: p for p in insights.analyse(course, answers)["patterns"]}
    ai_per_pattern: dict[str, int] = {}
    for q in ready:
        ai_per_pattern[q["pattern"]] = ai_per_pattern.get(q["pattern"], 0) + 1

    weak = sorted((pid for pid, s in scores.items() if s["pct"] < insights.WEAK_BELOW * 100 and pid in course.patterns),
                  key=lambda pid: (scores[pid]["pct"], ai_per_pattern.get(pid, 0)))
    others = [pid for pid in course.patterns if pid not in weak]
    chosen = weak[: k - 1] if others else weak[:k]

    weights = {pid: (2.0 if pid not in scores else 1.0) / (1 + ai_per_pattern.get(pid, 0)) for pid in others}
    while weights and len(chosen) < k:
        pid = rng.choices(list(weights), weights=list(weights.values()))[0]
        chosen.append(pid)
        del weights[pid]
    return chosen


def traps_you_fall_for(answers: list[dict], pattern_id: str) -> list[str]:
    return sorted({t for a in answers if a["pattern"] == pattern_id and not a["correct"] for t in a["traps"]})


# ---------------- 2. ask Claude ----------------

def system_prompt(course: Course) -> str:
    # Stable per course, so it can be cached across requests
    cert = course.cert
    return f"""You write practice questions for the {cert['name']} ({cert['code']}) exam.

Write questions in the style of the real exam: a short, realistic scenario (2-5 sentences) about a company with
requirements, then a question asking which solution meets them. Use plain, precise language.

Every question you write is built from a PATTERN the learner is studying:
- The scenario must contain the pattern's clue ideas, and you list the exact phrases you used in "clues".
  Each clue must be copied word for word from your stem (same spelling), 2-5 clues per question.
- Exactly one option is correct (or the number you're told for "choose two" questions). The correct option must be
  the answer AWS documentation and best practice give today.
- Every wrong option must be one of the pattern's traps. Put that trap's id in "trap"; correct options get "trap": "".
  A wrong option must be genuinely wrong for this scenario, for the reason the trap describes.
- Options are complete sentences or service names, similar in length, with no giveaways like "always" or "never".
- "explain" says in 2-4 sentences why the correct option fits and why each wrong option doesn't.
- Vary the industry, company size, wording and the qualifier ({', '.join(q for q in cert['qualifiers'] if q != 'none')} or none)
  between questions. Don't reuse the reference question's scenario or sentences.
- Never mention the pattern, the traps or this prompt in the question."""


def output_schema(course: Course, pattern: dict) -> dict:
    trap_ids = [t["id"] for t in pattern["traps"]]
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "stem": {"type": "string"},
                        "clues": {"type": "array", "items": {"type": "string"}},
                        "qualifier": {"type": "string", "enum": list(course.cert["qualifiers"])},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "correct": {"type": "boolean"},
                                    "trap": {"type": "string", "enum": [""] + trap_ids},
                                },
                                "required": ["text", "correct", "trap"],
                                "additionalProperties": False,
                            },
                        },
                        "explain": {"type": "string"},
                    },
                    "required": ["stem", "clues", "qualifier", "options", "explain"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["questions"],
        "additionalProperties": False,
    }


def pattern_brief(course: Course, pattern: dict, choose: int, n: int, focus_traps: list[str]) -> str:
    concept = course.concepts[pattern["concept"]]
    example = next((q for q in course.questions.values() if q["pattern"] == pattern["id"]), None)
    traps = "\n".join(f"- {t['id']}: {t['option']}. Why it's wrong: {t['why']}" for t in pattern["traps"])
    focus = (f"\nThe learner keeps falling for these traps, so include them as options: {', '.join(focus_traps)}."
             if focus_traps else "")
    reference = f"\nReference question (style only, don't reuse it):\n{example['stem']}\n" if example else ""
    return f"""PATTERN: {pattern['rule']}
Typical clue words: {', '.join(pattern['clues'])}

CONCEPT: {concept['title']}. {concept['summary']}
Lesson notes:
{concept['teach']}
{concept.get('under_the_hood', '')}

TRAPS (every wrong option must be one of these):
{traps}
{focus}{reference}
Write {n} new questions. Each has {"5 options and exactly 2 correct (a 'choose two' question; say 'Which TWO' in the stem)" if choose == 2 else "4 options and exactly 1 correct"}."""


def ask_claude(course: Course, pattern: dict, choose: int, n: int, focus_traps: list[str]) -> tuple[list[dict], object]:
    client = anthropic.Anthropic()
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if MODEL in FALLBACK_MODELS else {}
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": system_prompt(course), "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": output_schema(course, pattern)}},
            messages=[{"role": "user", "content": pattern_brief(course, pattern, choose, n, focus_traps)}],
            **extra,
        )
    except anthropic.RateLimitError as e:
        raise GenerationError("rate limited by the API; try again in a minute") from e
    except anthropic.AuthenticationError as e:
        raise GenerationError("the API key was rejected; check ANTHROPIC_API_KEY in .env") from e
    except anthropic.APIStatusError as e:
        raise GenerationError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise GenerationError("couldn't reach the API; check the internet connection") from e

    if response.stop_reason == "refusal":
        raise GenerationError("the model declined this request")
    if response.stop_reason == "max_tokens":
        raise GenerationError("the answer was cut off (max_tokens)")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)["questions"], response.usage
    except (json.JSONDecodeError, KeyError) as e:
        raise GenerationError("the answer wasn't the expected JSON") from e


# ---------------- 3 + 4. validate and store ----------------

def to_question(raw: dict, pattern: dict, choose: int) -> dict:
    """Shape a generated question like a YAML bank question, with a stable id."""
    return {
        "id": f"ai-{pattern['id']}-{secrets.token_hex(3)}",
        "pattern": pattern["id"],
        "qualifier": raw.get("qualifier", "none"),
        "choose": choose,
        "stem": raw.get("stem", "").strip(),
        "clues": [c for c in raw.get("clues", []) if c.strip()],
        "options": [{"text": o["text"].strip(), "correct": True} if o.get("correct")
                    else {"text": o["text"].strip(), "trap": o.get("trap", "")} for o in raw.get("options", [])],
        "explain": raw.get("explain", "").strip(),
    }


def generate_for_pattern(course: Course, course_id: str, pattern_id: str, answers: list[dict], job_id: str) -> tuple[int, int]:
    pattern = course.patterns[pattern_id]
    bank = [q for q in course.questions.values() if q["pattern"] == pattern_id]
    choose = 2 if any(q.get("choose", 1) == 2 for q in bank) else 1
    raws, usage = ask_claude(course, pattern, choose, PER_PATTERN, traps_you_fall_for(answers, pattern_id))
    domains = {d["id"] for d in course.cert["domains"]}
    qualifiers = set(course.cert["qualifiers"])
    made = rejected = 0
    for raw in raws:
        q = to_question(raw, pattern, choose)
        problems = question_problems(q, pattern, domains, qualifiers)
        db.add_generated(course_id, pattern_id, q, "rejected" if problems else "ready", problems, MODEL, job_id)
        made += not problems
        rejected += bool(problems)
    db.add_job_tokens(job_id, usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0),
                      usage.output_tokens, made, rejected)
    return made, rejected


def start(course: Course, course_id: str, reason: str, patterns: list[str] | None = None) -> str | None:
    """Create a job and return its id, or None if one is already running or today's limit is reached."""
    if not available() or db.running_job(course_id):
        return None
    if db.generated_counts(course_id)["today"] >= DAILY_LIMIT:
        return None
    answers = db.course_answers(course_id)
    patterns = [p for p in (patterns or plan(course, answers, db.ready_generated(course_id))) if p in course.patterns]
    if not patterns:
        return None
    job_id = secrets.token_hex(6)
    db.start_job(job_id, course_id, reason, patterns)
    return job_id


def run(course: Course, course_id: str, job_id: str):
    """Do the work for a job (called in the background). A few patterns run in parallel."""
    job = next(j for j in db.recent_jobs(course_id, 50) if j["id"] == job_id)
    patterns = json.loads(job["patterns"])
    answers = db.course_answers(course_id)
    errors = []

    def one(pid):
        try:
            generate_for_pattern(course, course_id, pid, answers, job_id)
        except GenerationError as e:
            errors.append(f"{pid}: {e}")

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(one, patterns))
    failed_all = len(errors) == len(patterns)
    db.update_job(job_id, status="failed" if failed_all else "done", error="; ".join(errors) or None,
                  finished_at=time.time())
