"""Load a certification course from content/<cert>/ and check that it hangs together.

A course is four kinds of YAML:
  cert.yaml            domains, weights, qualifiers
  concepts/*.yaml      one concept card per file
  patterns/*.yaml      a list of patterns (clues -> answer, plus traps)
  questions/*.yaml     a list of questions, each built from one pattern
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Links on concept cards should point at official documentation
OFFICIAL_LINKS = (
    "https://docs.aws.amazon.com/", "https://aws.amazon.com/",
    "https://learn.microsoft.com/", "https://cloud.google.com/", "https://kubernetes.io/",
)

REQUIRED = {
    "concept": ["id", "domain", "title", "summary", "teach", "under_the_hood", "other_clouds", "links"],
    "pattern": ["id", "concept", "clues", "rule", "traps"],
    "question": ["id", "pattern", "stem", "clues", "options", "explain"],
}


@dataclass
class Issue:
    level: str      # "error" stops the course loading cleanly; "warning" is a reminder
    where: str      # file and item, so you can jump straight to it
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


@dataclass
class Course:
    root: Path
    cert: dict
    concepts: dict = field(default_factory=dict)   # id -> concept
    patterns: dict = field(default_factory=dict)   # id -> pattern
    questions: dict = field(default_factory=dict)  # id -> question
    files: dict = field(default_factory=dict)      # (kind, id) -> file it came from
    issues: list = field(default_factory=list)     # problems found while loading


def load_course(root: Path) -> Course:
    """Read every YAML file in a course folder. Problems are recorded, not raised."""
    root = Path(root)
    issues: list[Issue] = []
    course = Course(root=root, cert=_read(root / "cert.yaml", issues) or {}, issues=issues)
    for kind, folder, target in [
        ("concept", "concepts", course.concepts),
        ("pattern", "patterns", course.patterns),
        ("question", "questions", course.questions),
    ]:
        for path in sorted((root / folder).glob("*.yaml")):
            data = _read(path, course.issues)
            entries = data if isinstance(data, list) else [data] if data else []
            for entry in entries:
                where = f"{folder}/{path.name}"
                if not isinstance(entry, dict) or "id" not in entry:
                    course.issues.append(Issue("error", where, f"a {kind} has no id"))
                    continue
                if entry["id"] in target:
                    first = course.files[(kind, entry["id"])]
                    course.issues.append(Issue("error", where, f"duplicate {kind} id '{entry['id']}' (first defined in {first})"))
                    continue
                target[entry["id"]] = entry
                course.files[(kind, entry["id"])] = where
    return course


def _read(path: Path, issues: list):
    try:
        return yaml.safe_load(path.read_text())
    except FileNotFoundError:
        issues.append(Issue("error", path.name, "file not found"))
    except yaml.YAMLError as e:
        issues.append(Issue("error", path.name, f"not valid YAML: {e}"))
    return None


def validate(course: Course) -> list[Issue]:
    """Every check the content must pass. Returns load problems plus anything found here."""
    issues = list(course.issues)
    domains = {d["id"] for d in course.cert.get("domains", [])}
    qualifiers = set(course.cert.get("qualifiers", ["none"]))

    def where(kind, item_id):
        return f"{course.files[(kind, item_id)]} [{item_id}]"

    def missing_fields(kind, item):
        gone = [f for f in REQUIRED[kind] if not item.get(f)]
        if gone:
            issues.append(Issue("error", where(kind, item["id"]), f"missing {', '.join(gone)}"))
        return bool(gone)

    # ---- concepts ----
    for c in course.concepts.values():
        if missing_fields("concept", c):
            continue
        w = where("concept", c["id"])
        if c["domain"] not in domains:
            issues.append(Issue("error", w, f"domain '{c['domain']}' isn't one of {sorted(domains)}"))
        for rel in c.get("related", []):
            if rel not in course.concepts:
                issues.append(Issue("warning", w, f"related concept '{rel}' isn't written yet"))
        for cloud in ("azure", "gcp"):
            if cloud not in c["other_clouds"]:
                issues.append(Issue("warning", w, f"other_clouds has no {cloud} entry"))
        for link in c["links"]:
            if not str(link.get("url", "")).startswith(OFFICIAL_LINKS):
                issues.append(Issue("warning", w, f"link isn't official docs: {link.get('url')}"))

    # ---- patterns ----
    trap_owner = {}   # trap id -> pattern id; trap ids must be unique so mistake stats add up
    for p in course.patterns.values():
        if missing_fields("pattern", p):
            continue
        w = where("pattern", p["id"])
        if p["concept"] not in course.concepts:
            issues.append(Issue("error", w, f"concept '{p['concept']}' doesn't exist"))
        for t in p["traps"]:
            if "id" not in t or "why" not in t:
                issues.append(Issue("error", w, "every trap needs an id and a why"))
                continue
            if t["id"] in trap_owner:
                issues.append(Issue("error", w, f"trap id '{t['id']}' is already used by pattern '{trap_owner[t['id']]}'"))
            trap_owner[t["id"]] = p["id"]

    # ---- questions ----
    used_traps, used_patterns = set(), set()
    for q in course.questions.values():
        if missing_fields("question", q):
            continue
        w = where("question", q["id"])
        pattern = course.patterns.get(q["pattern"])
        if pattern is None:
            issues.append(Issue("error", w, f"pattern '{q['pattern']}' doesn't exist"))
            continue
        used_patterns.add(pattern["id"])
        pattern_traps = {t.get("id") for t in pattern.get("traps", [])}

        if q.get("domain") and q["domain"] not in domains:
            issues.append(Issue("error", w, f"domain '{q['domain']}' isn't one of {sorted(domains)}"))
        if q.get("qualifier", "none") not in qualifiers:
            issues.append(Issue("error", w, f"qualifier '{q['qualifier']}' isn't one of {sorted(qualifiers)}"))

        stem = q["stem"].lower()
        for clue in q["clues"]:
            if str(clue).lower() not in stem:
                issues.append(Issue("error", w, f"clue '{clue}' doesn't appear in the question text"))

        options = q["options"]
        choose = q.get("choose", 1)
        if not 3 <= len(options) <= 6:
            issues.append(Issue("error", w, f"has {len(options)} options; use 3 to 6"))
        correct = [o for o in options if o.get("correct")]
        if len(correct) != choose:
            issues.append(Issue("error", w, f"choose is {choose} but {len(correct)} option(s) are marked correct"))
        for n, o in enumerate(options, start=1):
            if not o.get("text"):
                issues.append(Issue("error", w, f"option {n} has no text"))
            if o.get("correct") and o.get("trap"):
                issues.append(Issue("error", w, f"option {n} is marked correct and also has a trap"))
            if not o.get("correct"):
                if not o.get("trap"):
                    issues.append(Issue("error", w, f"wrong option {n} has no trap, so a miss can't be tracked"))
                elif o["trap"] not in pattern_traps:
                    issues.append(Issue("error", w, f"option {n} uses trap '{o['trap']}', which pattern '{pattern['id']}' doesn't define"))
                else:
                    used_traps.add(o["trap"])

    # ---- coverage reminders ----
    for p in course.patterns.values():
        if p["id"] not in used_patterns:
            issues.append(Issue("warning", where("pattern", p["id"]), "no questions use this pattern yet"))
        for t in p.get("traps", []):
            if t.get("id") in trap_owner and t["id"] not in used_traps and p["id"] in used_patterns:
                issues.append(Issue("warning", where("pattern", p["id"]), f"no question offers trap '{t['id']}' yet"))
    patterned = {p.get("concept") for p in course.patterns.values()}
    for c in course.concepts.values():
        if c["id"] not in patterned:
            issues.append(Issue("warning", where("concept", c["id"]), "no patterns for this concept yet"))

    return issues
