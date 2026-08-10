from reviewer_agent.matcher import match_feature_to_files, rank_all_features, unmatched_files
from reviewer_agent.models import AcceptanceCriterion, CodeFile, Feature


def make_feature():
    return Feature(
        id="F1",
        title="User Login",
        description="Allow a user to log in with a password.",
        acceptance_criteria=[
            AcceptanceCriterion(id="F1-AC1", text="Reject invalid login password attempts."),
        ],
    )


def test_matches_relevant_file_over_irrelevant_one():
    feature = make_feature()
    login_file = CodeFile(path="login.py", content="def login(password):\n    check_password(password)\n")
    unrelated_file = CodeFile(path="billing.py", content="def charge_credit_card(amount):\n    pass\n")

    matches = match_feature_to_files(feature, [login_file, unrelated_file])

    assert len(matches) == 1
    assert matches[0].file.path == "login.py"


def test_rank_all_features_and_unmatched_files():
    feature = make_feature()
    login_file = CodeFile(path="login.py", content="def login(password):\n    check_password(password)\n")
    unrelated_file = CodeFile(path="billing.py", content="def charge_credit_card(amount):\n    pass\n")

    matches_by_feature = rank_all_features([feature], [login_file, unrelated_file])
    assert "F1" in matches_by_feature
    assert [m.file.path for m in matches_by_feature["F1"]] == ["login.py"]

    unmatched = unmatched_files([login_file, unrelated_file], matches_by_feature)
    assert unmatched == ["billing.py"]


def test_no_matches_when_no_keywords():
    feature = Feature(id="F1", title="", description="", acceptance_criteria=[])
    files = [CodeFile(path="a.py", content="print(1)")]
    assert match_feature_to_files(feature, files) == []
