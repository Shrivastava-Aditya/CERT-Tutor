"""Check a course folder for broken links between concepts, patterns and questions.

Usage:  python tools/validate.py content/aws-saa-c03
Exits with 1 if there are errors, so it can gate commits or CI later.
"""
import sys
from pathlib import Path

# Make "import app..." work when this file is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.content import load_course, validate  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    course = load_course(Path(argv[1]))
    issues = validate(course)
    for issue in sorted(issues, key=lambda i: (i.level != "error", i.where)):
        print(issue)
    errors = sum(i.level == "error" for i in issues)
    print(
        f"\n{course.cert.get('code', argv[1])}: {len(course.concepts)} concepts, "
        f"{len(course.patterns)} patterns, {len(course.questions)} questions · "
        f"{errors} errors, {len(issues) - errors} warnings"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
