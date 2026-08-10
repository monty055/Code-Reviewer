from pathlib import Path

from reviewer_agent.requirements_parser import parse_requirements_file, parse_requirements_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_multiple_features_with_explicit_ac_heading():
    features = parse_requirements_file(str(FIXTURES / "sample_prd.md"))

    assert [f.title for f in features] == ["Login", "Logout"]

    login = features[0]
    assert "log in" in login.description.lower()
    assert [c.id for c in login.acceptance_criteria] == ["AC-1", "AC-2"]
    assert login.acceptance_criteria[0].text == "Reject invalid passwords."
    assert login.acceptance_criteria[1].text == "Issue a token on success."


def test_falls_back_to_bullets_when_no_explicit_ac_heading():
    features = parse_requirements_file(str(FIXTURES / "sample_prd.md"))

    logout = features[1]
    assert len(logout.acceptance_criteria) == 2
    assert "session token" in logout.acceptance_criteria[0].text


def test_generates_ids_when_missing():
    text = """# Widget

    - Does a thing
    - Does another thing
    """
    features = parse_requirements_text(text)
    assert len(features) == 1
    ids = [c.id for c in features[0].acceptance_criteria]
    assert ids == ["F1-AC1", "F1-AC2"]


def test_document_with_no_headings_becomes_single_feature():
    text = "- Must do X\n- Must do Y\n"
    features = parse_requirements_text(text, source_name="notes.txt")
    assert len(features) == 1
    assert features[0].title == "notes.txt"
    assert len(features[0].acceptance_criteria) == 2


def test_empty_document_yields_no_features():
    assert parse_requirements_text("") == []
