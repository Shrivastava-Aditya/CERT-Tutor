"""AI tutor chat: explains concepts and your mistakes, knowing the concept card and your weak spots.

Token savings built in:
  - prompt caching: the tutor rules + concept card are a cached prefix (re-read at ~1/10 the price each turn),
    and the conversation itself is cached so far, so each new turn only pays full price for the new message
  - short history: only the last MAX_TURNS messages are sent
  - optional Headroom proxy (HEADROOM_URL) in front of the API, with usage logged either way so the two can be compared
"""
import os

import anthropic

from app import db, insights
from app.content import Course

MODEL = os.environ.get("TUTOR_MODEL", "claude-opus-5-5")
HEADROOM_URL = os.environ.get("HEADROOM_URL", "").strip()
DAILY_LIMIT = int(os.environ.get("TUTOR_DAILY_LIMIT", "200"))
MAX_TURNS = 20             # messages of history sent with each request
MAX_CHARS = 4000           # per user message
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

MODES = {
    "explain": "Explain clearly and concretely, building on what the learner already knows.",
    "quiz": "Quiz the learner Socratically: ask one question at a time, wait for their answer, then give feedback and the next question. Don't give the answer before they try.",
    "compare": "Compare how AWS, Microsoft Azure and Google Cloud solve this, service by service, and point out the differences that matter in practice.",
    "why-wrong": "The learner just got a practice question wrong. Explain why their choice was wrong, which clue words in the scenario point to the right answer, and how to spot this trap next time.",
}


class TutorError(Exception):
    pass


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def client() -> anthropic.Anthropic:
    # With HEADROOM_URL set, requests go through the Headroom proxy, which compresses context before forwarding to the API
    return anthropic.Anthropic(base_url=HEADROOM_URL) if HEADROOM_URL else anthropic.Anthropic()


def system_blocks(course: Course, concept: dict | None) -> list[dict]:
    """Stable for a given course + concept, so it can be cached across every turn of the conversation."""
    rules = f"""You are a patient, precise tutor helping one learner prepare for the {course.cert['name']} ({course.cert['code']}) exam.
They run a homelab (Linux server, Docker, Samba, an external drive) and learn best when cloud ideas are tied to things they can see.

How to teach:
- Answer what was asked, in plain language, in short paragraphs or a short list. Aim for under 200 words unless asked for more.
- Explain what happens under the hood when it helps, and connect ideas to real examples or to the learner's homelab.
- When a question is about exam strategy, name the clue words and the trap.
- Be accurate. If something depends on current AWS details you're unsure of, say so and point to the official AWS documentation.
- Use Markdown for **bold**, `code` and lists. No headings."""
    blocks = [{"type": "text", "text": rules}]
    if concept:
        card = "\n\n".join(f"{label}:\n{concept.get(field)}" for field, label in [
            ("summary", "Summary"), ("teach", "Lesson"), ("under_the_hood", "Under the hood"), ("case_study", "Case study"),
        ] if concept.get(field))
        clouds = "; ".join(f"{k}: {v}" for k, v in concept.get("other_clouds", {}).items())
        blocks.append({"type": "text", "text": f"CURRENT CONCEPT: {concept['title']}\n\n{card}\n\nOther clouds: {clouds}"})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def learner_profile(course: Course, concept_id: str | None) -> str:
    analysis = insights.analyse(course, db.course_answers(course.cert["id"]))
    if not analysis["total"]:
        return "The learner hasn't answered any practice questions yet."
    weak = [p["rule"] for p in analysis["weak"] if not concept_id or p["concept"] == concept_id][:4]
    traps = [f"{t['option']} (x{t['count']})" for t in analysis["traps"] if not concept_id or course.patterns[t["pattern"]]["concept"] == concept_id][:4]
    lines = [f"Overall: {analysis['pct']}% correct over {analysis['total']} answers."]
    if weak:
        lines.append("Weak patterns here: " + "; ".join(weak))
    if traps:
        lines.append("Traps they fall for here: " + "; ".join(traps))
    return "\n".join(lines)


def question_context(question: dict, chosen: list[str]) -> str:
    lines = [f"PRACTICE QUESTION:\n{question['stem']}", "Options:"]
    for o in question["options"]:
        tag = []
        if o["correct"]:
            tag.append("correct answer")
        if o["id"] in chosen:
            tag.append("learner's choice")
        if o.get("trap_why") and o["id"] in chosen and not o["correct"]:
            tag.append(f"trap: {o['trap_why']}")
        lines.append(f"- {o['text']}" + (f"  [{', '.join(tag)}]" if tag else ""))
    lines += [f"Pattern: {question['rule']}", f"Clue words: {', '.join(question['clues'])}"]
    return "\n".join(lines)


def build_messages(history: list[dict], mode: str, profile: str, context: str) -> list[dict]:
    """The conversation, trimmed, with the learner profile and question context on the first turn."""
    history = [{"role": m["role"], "content": str(m["content"])[:MAX_CHARS]}
               for m in history if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-MAX_TURNS:]
    while history and history[0]["role"] != "user":
        history.pop(0)            # the API needs the conversation to start with the learner
    if not history:
        raise TutorError("Say something to the tutor first.")
    preamble = f"[Teaching mode: {MODES[mode]}]\n[Learner profile]\n{profile}\n"
    if context:
        preamble += f"\n{context}\n"
    history[0] = {"role": "user", "content": f"{preamble}\n{history[0]['content']}"}
    return history


def stream_reply(course: Course, concept: dict | None, mode: str, history: list[dict], context: str = ""):
    """Yields the reply text as it's written, then logs the token usage."""
    if not available():
        raise TutorError("Add ANTHROPIC_API_KEY to .env to use the tutor.")
    if db.tutor_replies_today(course.cert["id"]) >= DAILY_LIMIT:
        raise TutorError(f"Today's tutor limit ({DAILY_LIMIT} replies) is used up. Change TUTOR_DAILY_LIMIT in .env to raise it.")
    mode = mode if mode in MODES else "explain"
    messages = build_messages(history, mode, learner_profile(course, concept["id"] if concept else None), context)
    params = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": system_blocks(course, concept),
        "messages": messages,
        "cache_control": {"type": "ephemeral"},     # also cache the conversation so far, so the next turn re-reads it cheaply
        "output_config": {"effort": "medium"},
    }
    # The refusal fallback is a beta feature; leave it out when an unknown proxy sits in between
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if MODEL in FALLBACK_MODELS and not HEADROOM_URL else {}
    try:
        with client().beta.messages.stream(**params, **extra) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
    except anthropic.RateLimitError as e:
        raise TutorError("The API is rate limiting requests. Try again in a minute.") from e
    except anthropic.AuthenticationError as e:
        raise TutorError("The API key was rejected. Check ANTHROPIC_API_KEY in .env.") from e
    except anthropic.APIStatusError as e:
        raise TutorError(f"The API returned an error ({e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise TutorError("Couldn't reach the API" + (" through Headroom" if HEADROOM_URL else "") + ".") from e
    if final.stop_reason == "refusal":
        yield "\n\n_The tutor can't help with that one._"
    db.log_tutor_usage(course.cert["id"], concept["id"] if concept else None, mode, final.model, bool(HEADROOM_URL), final.usage)
