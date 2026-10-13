"""Turn a loaded Course into what the Learn pages need."""
from app.content import Course
from app.icons import icon_url

TABS = [  # (concept field, tab id, tab label)
    ("teach", "teach", "Teach"),
    ("under_the_hood", "under-the-hood", "Under the hood"),
    ("observe", "see-it", "See it"),
    ("case_study", "case-study", "Case study"),
    ("other_clouds", "other-clouds", "Other clouds"),
    ("links", "links", "Links"),
]

CLOUD_NAMES = {"azure": "Microsoft Azure", "gcp": "Google Cloud"}


def ordered_concepts(course: Course) -> list[dict]:
    """Concepts grouped in exam-domain order, then alphabetically."""
    order = {d["id"]: i for i, d in enumerate(course.cert.get("domains", []))}
    return sorted(course.concepts.values(), key=lambda c: (order.get(c["domain"], 99), c["title"].lower()))


def concept_stats(course: Course) -> dict:
    """concept id -> {patterns: [...], questions: n}"""
    stats = {cid: {"patterns": [], "questions": 0} for cid in course.concepts}
    for p in course.patterns.values():
        if p["concept"] in stats:
            stats[p["concept"]]["patterns"].append(p)
    for q in course.questions.values():
        p = course.patterns.get(q["pattern"])
        if p and p["concept"] in stats:
            stats[p["concept"]]["questions"] += 1
    return stats


def domains_with_concepts(course: Course) -> list[dict]:
    concepts = ordered_concepts(course)
    return [
        {**d, "concepts": [c for c in concepts if c["domain"] == d["id"]]}
        for d in course.cert.get("domains", [])
    ]


def graph(course: Course, course_id: str) -> dict:
    """Nodes and links for the concept map. Related concepts that aren't written yet become ghost nodes."""
    stats = concept_stats(course)
    nodes = {
        c["id"]: {
            "id": c["id"], "title": c["title"], "domain": c["domain"], "written": True,
            "url": f"/course/{course_id}/{c['id']}", "icon": icon_url(c.get("icon", "")),
            "questions": stats[c["id"]]["questions"],
        }
        for c in course.concepts.values()
    }
    links = set()
    for c in course.concepts.values():
        for rel in c.get("related", []):
            if rel not in nodes:
                nodes[rel] = {"id": rel, "title": rel.replace("-", " "), "domain": None, "written": False}
            links.add(tuple(sorted((c["id"], rel))))
    return {"nodes": list(nodes.values()), "links": [{"source": a, "target": b} for a, b in sorted(links)]}


def neighbours(course: Course, concept_id: str) -> tuple[dict | None, dict | None]:
    """Previous and next concept in course order."""
    concepts = ordered_concepts(course)
    ids = [c["id"] for c in concepts]
    i = ids.index(concept_id)
    return (concepts[i - 1] if i > 0 else None, concepts[i + 1] if i < len(concepts) - 1 else None)
