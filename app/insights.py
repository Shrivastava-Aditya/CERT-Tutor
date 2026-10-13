"""Weakness analysis: turn every recorded answer into 'what to work on next'."""
from collections import Counter, defaultdict

from app.content import Course

WEAK_BELOW = 0.7    # a pattern under 70% correct counts as weak
SLOW_SECONDS = 150  # well over the ~2 minutes per question the real exam allows


def _pct(c, t):
    return round(100 * c / t) if t else 0


def analyse(course: Course, answers: list[dict]) -> dict:
    total = len(answers)
    correct = sum(a["correct"] for a in answers)

    # ---- by domain ----
    domains = []
    for d in course.cert["domains"]:
        rows = [a for a in answers if a["domain"] == d["id"]]
        c = sum(a["correct"] for a in rows)
        domains.append({**d, "correct": c, "total": len(rows), "pct": _pct(c, len(rows))})

    # ---- by pattern (worst first) ----
    grouped = defaultdict(list)
    for a in answers:
        grouped[a["pattern"]].append(a)
    patterns = []
    for pid, rows in grouped.items():
        p = course.patterns.get(pid)
        if not p:
            continue   # the pattern was renamed or removed since you answered
        concept = course.concepts.get(p["concept"], {})
        c = sum(r["correct"] for r in rows)
        patterns.append({
            "id": pid, "rule": p["rule"], "clues": p["clues"],
            "concept": p["concept"], "concept_title": concept.get("title", p["concept"]),
            "correct": c, "total": len(rows), "pct": _pct(c, len(rows)),
            "last_correct": bool(rows[-1]["correct"]),
        })
    patterns.sort(key=lambda p: (p["pct"], -p["total"]))
    weak = [p for p in patterns if p["pct"] < WEAK_BELOW * 100]

    # ---- traps you fall for ----
    trap_info = {t["id"]: {**t, "pattern": p["id"], "rule": p["rule"]} for p in course.patterns.values() for t in p["traps"]}
    counts = Counter(t for a in answers if not a["correct"] for t in a["traps"])
    traps = [{**trap_info[t], "count": n} for t, n in counts.most_common() if t in trap_info]

    # ---- qualifiers ("most cost-effective", "least overhead"...) ----
    qualifiers = []
    for q in course.cert.get("qualifiers", []):
        if q == "none":
            continue
        rows = [a for a in answers if a["qualifier"] == q]
        if rows:
            c = sum(a["correct"] for a in rows)
            qualifiers.append({"id": q, "correct": c, "total": len(rows), "pct": _pct(c, len(rows))})
    qualifiers.sort(key=lambda q: q["pct"])

    # ---- time ----
    timed = [a["seconds"] for a in answers if a["seconds"]]
    avg_seconds = round(sum(timed) / len(timed)) if timed else 0
    slow = sum(1 for s in timed if s > SLOW_SECONDS)

    # ---- concept mastery (feeds the map and the tracks later) ----
    mastery = {}
    for cid in course.concepts:
        rows = [a for a in answers if a["concept"] == cid]
        if not rows:
            continue
        pct = _pct(sum(r["correct"] for r in rows), len(rows))
        mastery[cid] = "mastered" if pct >= 85 and len(rows) >= 3 else "learning"

    return {
        "total": total, "correct": correct, "pct": _pct(correct, total),
        "domains": domains, "patterns": patterns, "weak": weak, "traps": traps,
        "qualifiers": qualifiers, "avg_seconds": avg_seconds, "slow": slow, "mastery": mastery,
    }
