from reviewer_agent.analyzer import evaluate_criterion_heuristic, evaluate_feature, review
from reviewer_agent.models import AcceptanceCriterion, CodeFile, CriterionStatus, Feature


def test_met_when_strong_keyword_overlap():
    criterion = AcceptanceCriterion(id="AC-1", text="Reject invalid password login attempts")
    code = CodeFile(
        path="login.py",
        content="def login(password):\n    if invalid(password):\n        reject_attempt()\n",
    )

    result = evaluate_criterion_heuristic(criterion, [code])

    assert result.status == CriterionStatus.MET
    assert result.evidence


def test_not_met_when_no_overlap():
    criterion = AcceptanceCriterion(id="AC-1", text="Send a reminder email before due date")
    code = CodeFile(path="login.py", content="def login(password):\n    return True\n")

    result = evaluate_criterion_heuristic(criterion, [code])

    assert result.status == CriterionStatus.NOT_MET


def test_needs_review_when_no_matched_files():
    criterion = AcceptanceCriterion(id="AC-1", text="Send a reminder email before due date")

    result = evaluate_criterion_heuristic(criterion, [])

    assert result.status == CriterionStatus.NEEDS_REVIEW


def test_evaluate_feature_end_to_end():
    feature = Feature(
        id="F1",
        title="User Login",
        description="Allow a user to log in.",
        acceptance_criteria=[
            AcceptanceCriterion(id="F1-AC1", text="Reject invalid login passwords"),
            AcceptanceCriterion(id="F1-AC2", text="Send confirmation email after login"),
        ],
    )
    files = [
        CodeFile(
            path="login.py",
            content="def login(password):\n    if invalid(password):\n        return None\n",
        )
    ]

    report = evaluate_feature(feature, files)

    assert report.matched_files == ["login.py"]
    assert len(report.criterion_results) == 2
    assert report.criterion_results[0].status in (
        CriterionStatus.MET,
        CriterionStatus.PARTIALLY_MET,
    )
    assert report.criterion_results[1].status == CriterionStatus.NOT_MET
    assert report.coverage == 0.5


def test_review_produces_report_for_all_features():
    features = [
        Feature(
            id="F1",
            title="Login",
            acceptance_criteria=[AcceptanceCriterion(id="F1-AC1", text="Reject invalid login password")],
        )
    ]
    files = [CodeFile(path="login.py", content="def login(password):\n    reject_invalid(password)\n")]

    report = review(features, files, requirements_source="req.md", codebase_source="src/")

    assert len(report.feature_reports) == 1
    assert report.overall_coverage == 1.0
