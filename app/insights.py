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


def answer_log(course: Course, answers: list[dict], shown: dict[str, dict[str, dict]]) -> list[dict]:
    """Every answer you've given, newest first, with the question text, your pick, the right answer and the time taken."""
    domain_names = {d["id"]: d["name"] for d in course.cert["domains"]}
    log = []
    for a in reversed(answers):
        q = shown.get(a["attempt_id"], {}).get(a["question_id"])
        if q is None:
            continue
        picked = [o for o in q["options"] if o["id"] in a["chosen"]]
        concept = course.concepts.get(a["concept"], {})
        log.append({
            "attempt_id": a["attempt_id"], "question_id": a["question_id"], "when": a["answered_at"],
            "stem": q["stem"], "rule": q.get("rule", ""), "source": a["source"],
            "concept": a["concept"], "concept_title": concept.get("title", a["concept"]),
            "domain": a["domain"], "domain_name": domain_names.get(a["domain"], a["domain"]),
            "correct": bool(a["correct"]), "seconds": round(a["seconds"]) if a["seconds"] else None, "flagged": bool(a["flagged"]),
            "picked": [o["text"] for o in picked],
            "right": [o["text"] for o in q["options"] if o["correct"]],
            "trap_why": next((o.get("trap_why") for o in picked if not o["correct"] and o.get("trap_why")), None),
        })
    return log


def by_module(course: Course, log: list[dict]) -> list[dict]:
    """Domains in exam order, each with its concepts: accuracy, time, and the questions you got wrong."""
    out = []
    for d in course.cert["domains"]:
        concepts = []
        for cid, c in course.concepts.items():
            if c["domain"] != d["id"]:
                continue
            rows = [r for r in log if r["concept"] == cid]
            if not rows:
                continue
            timed = [r["seconds"] for r in rows if r["seconds"]]
            right = sum(r["correct"] for r in rows)
            concepts.append({
                "id": cid, "title": c["title"], "answered": len(rows), "correct": right, "pct": _pct(right, len(rows)),
                "avg_seconds": round(sum(timed) / len(timed)) if timed else None,
                "wrong": [r for r in rows if not r["correct"]],
            })
        concepts.sort(key=lambda c: (c["pct"], -c["answered"]))
        rows = [r for r in log if r["domain"] == d["id"]]
        right = sum(r["correct"] for r in rows)
        timed = [r["seconds"] for r in rows if r["seconds"]]
        out.append({**d, "concepts": concepts, "answered": len(rows), "correct": right, "pct": _pct(right, len(rows)),
                    "avg_seconds": round(sum(timed) / len(timed)) if timed else None})
    return out


def time_stats(log: list[dict]) -> dict:
    timed = [r for r in log if r["seconds"]]
    total = sum(r["seconds"] for r in timed)
    right = [r["seconds"] for r in timed if r["correct"]]
    wrong = [r["seconds"] for r in timed if not r["correct"]]
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None
    return {
        "total_seconds": total, "avg": avg([r["seconds"] for r in timed]),
        "avg_right": avg(right), "avg_wrong": avg(wrong),
        "slowest": sorted(timed, key=lambda r: r["seconds"], reverse=True)[:8],
        "over_limit": sum(1 for r in timed if r["seconds"] > SLOW_SECONDS),
    }
