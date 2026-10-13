from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_and_tracks_load():
    assert client.get("/").status_code == 200
    page = client.get("/tracks")
    assert page.status_code == 200
    # The SAA station links to its course
    assert 'href="/course/aws-saa-c03"' in page.text


def test_course_page_lists_concepts_by_domain():
    page = client.get("/course/aws-saa-c03")
    assert page.status_code == 200
    for title in ["Amazon EFS", "Amazon S3 storage classes", "Design Resilient Architectures"]:
        assert title in page.text
    assert "data-concept-map" in page.text


def test_concept_page_has_tabs_patterns_and_markdown():
    page = client.get("/course/aws-saa-c03/ebs-volume-types")
    assert page.status_code == 200
    assert 'id="tab-under-the-hood"' in page.text
    assert "Exam patterns" in page.text
    assert "<table>" in page.text          # the Markdown table in the Teach text was rendered
    assert "io2 Block Express" in page.text


def test_unknown_course_and_concept_are_404():
    assert client.get("/course/nope").status_code == 404
    assert client.get("/course/aws-saa-c03/nope").status_code == 404
    # Path tricks can't reach files outside content/
    assert client.get("/course/..%2Fapp").status_code == 404
