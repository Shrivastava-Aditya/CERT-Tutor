"""Turn course questions into exam questions: build the pool, pick by domain weight, shuffle, grade, score."""
import random

from app.content import Course

MODES = {   # name: (questions, minutes, label)
    "full": (65, 130, "Full exam"),
    "half": (30, 60, "Half exam"),
    "sprint": (10, 20, "Sprint"),
}
XP_CORRECT = 10
XP_COMEBACK = 5     # bonus for getting right a pattern you've missed before


def enrich(course: Course, q: dict, source: str) -> dict:
    """A self-contained question: everything the exam and the review need, with stable option ids."""
    pattern = course.patterns[q["pattern"]]
    concept = course.concepts[pattern["concept"]]
    traps = {t["id"]: t for t in pattern["traps"]}
    return {
        "id": q["id"],
        "source": source,
        "pattern": pattern["id"],
        "rule": pattern["rule"],
        "concept": concept["id"],
        "concept_title": concept["title"],
        "domain": q.get("domain") or concept["domain"],
        "qualifier": q.get("qualifier", "none"),
        "choose": q.get("choose", 1),
        "stem": q["stem"],
        "clues": q.get("clues", []),
        "explain": q["explain"],
        "options": [
            {
                "id": f"o{i}",
                "text": o["text"],
                "correct": bool(o.get("correct")),
                "trap": o.get("trap"),
                "trap_why": traps.get(o.get("trap"), {}).get("why"),
            }
            for i, o in enumerate(q["options"])
        ],
    }


def pool(course: Course, concept: str | None = None, generated: list[dict] | None = None) -> list[dict]:
    """Bank questions from the YAML, plus any AI-generated ones that passed the validator."""
    questions = [enrich(course, q, "bank") for q in course.questions.values()]
    questions += [enrich(course, q, "ai") for q in (generated or []) if q["pattern"] in course.patterns]
    if concept:
        questions = [q for q in questions if q["concept"] == concept]
    return questions


def pick(course: Course, questions: list[dict], n: int, rng=random, seen: dict | None = None) -> list[dict]:
    """Choose n questions with domain counts proportional to the exam weights, topping up from other domains if one runs short.
    Within a domain, questions you've answered fewer times come first, so fresh AI questions get used."""
    seen = seen or {}
    freshest = lambda q: (seen.get(q["id"], 0), rng.random())
    if n >= len(questions):
        chosen = list(questions)
        rng.shuffle(chosen)
        return chosen
    by_domain: dict[str, list] = {}
    for q in questions:
        by_domain.setdefault(q["domain"], []).append(q)
    for qs in by_domain.values():
        qs.sort(key=freshest)

    weights = {d["id"]: d["weight"] for d in course.cert["domains"]}
    raw = {d: n * weights.get(d, 0) / 100 for d in by_domain}
    quota = {d: int(v) for d, v in raw.items()}
    for d in sorted(raw, key=lambda d: raw[d] - quota[d], reverse=True)[: n - sum(quota.values())]:
        quota[d] += 1

    chosen = []
    for d, qs in by_domain.items():
        chosen += qs[: quota[d]]
    leftovers = [q for d, qs in by_domain.items() for q in qs[quota[d]:]]
    chosen += leftovers[: n - len(chosen)]
    rng.shuffle(chosen)
    return chosen


def shuffled(questions: list[dict], rng=random) -> list[dict]:
    """Copy each question with its options in a random order, so letter positions can't be memorised."""
    out = []
    for q in questions:
        options = list(q["options"])
        rng.shuffle(options)
        out.append({**q, "options": options})
    return out


def public(q: dict, reveal: bool) -> dict:
    """What the browser gets. In exam mode, nothing that gives the answer away."""
    if reveal:
        return q
    return {
        "id": q["id"], "choose": q["choose"], "stem": q["stem"], "domain": q["domain"],
        "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]],
    }


def grade(q: dict, chosen: list[str]) -> tuple[bool, list[str]]:
    """Correct only if exactly the right options were chosen (no partial credit for 'choose two'). Also returns the traps picked."""
    right = {o["id"] for o in q["options"] if o["correct"]}
    picked = set(chosen)
    traps = [o["trap"] for o in q["options"] if o["id"] in picked and o.get("trap")]
    return picked == right, traps


def scaled_score(correct: int, total: int) -> int:
    """AWS doesn't publish its scaling, so map the percentage straight onto 100–1000 (720 ≈ 69%)."""
    return round(100 + 900 * correct / total) if total else 100
