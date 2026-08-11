from reviewer_agent.gap_analysis import (
    analyze_design_gaps,
    analyze_test_data_requirements,
    analyze_user_story_gaps,
    run_gap_analysis,
)
from reviewer_agent.models import AcceptanceCriterion, Feature
from reviewer_agent.requirements_parser import parse_requirements_text


def make_feature(title="Task Creation", description="", criteria=None):
    return Feature(
        id="F1",
        title=title,
        description=description,
        acceptance_criteria=criteria or [],
    )


def test_missing_acceptance_criteria_is_high_severity_gap():
    feature = make_feature(description="As a user, I want to create a task so that I can track work.")
    gaps = analyze_user_story_gaps(feature)
    assert any("no acceptance criteria" in g.description.lower() for g in gaps)
    assert any(g.severity.value == "High" for g in gaps)


def test_well_formed_story_has_no_role_goal_benefit_gap():
    feature = make_feature(
        description="As a logged-in user, I want to create a task so that I can track my work.",
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text="A task cannot be created without a title."),
            AcceptanceCriterion(id="F1-AC2", text="The system must reject a task with an invalid due date."),
        ],
    )
    gaps = analyze_user_story_gaps(feature)
    assert not any("does not follow the standard user-story format" in g.description for g in gaps)


def test_missing_role_goal_benefit_flagged():
    feature = make_feature(
        description="Users can create tasks.",
        criteria=[AcceptanceCriterion(id="F1-AC1", text="A task must have a title and a due date.")],
    )
    gaps = analyze_user_story_gaps(feature)
    assert any("does not follow the standard user-story format" in g.description for g in gaps)


def test_vague_criterion_flagged():
    feature = make_feature(
        description="As a user, I want a good experience so that I am happy.",
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text="The response should be fast and user-friendly."),
            AcceptanceCriterion(id="F1-AC2", text="Reject invalid input with a clear error message."),
        ],
    )
    gaps = analyze_user_story_gaps(feature)
    assert any("vague/subjective language" in g.description for g in gaps)


def test_missing_negative_case_flagged_when_only_happy_path():
    feature = make_feature(
        description="As a user, I want to create a task so that I can track work.",
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text="A newly created task defaults to status pending."),
        ],
    )
    gaps = analyze_user_story_gaps(feature)
    assert any("only describes happy-path behavior" in g.description for g in gaps)


def test_negative_case_present_avoids_happy_path_gap():
    feature = make_feature(
        description="As a user, I want to create a task so that I can track work.",
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text="A task cannot be created without a title."),
        ],
    )
    gaps = analyze_user_story_gaps(feature)
    assert not any("only describes happy-path behavior" in g.description for g in gaps)


def test_design_gaps_flag_absent_categories():
    feature = make_feature(
        description="As a user, I want to create a task so that I can track work.",
        criteria=[AcceptanceCriterion(id="F1-AC1", text="A task cannot be created without a title.")],
    )
    gaps = analyze_design_gaps(feature)
    categories = {g.description for g in gaps}
    assert any("security" in c.lower() for c in categories)
    assert any("performance" in c.lower() for c in categories)


def test_design_gaps_skip_categories_that_are_covered():
    feature = make_feature(
        description="As a user, I want to log in securely so that my account is protected.",
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text="Passwords must be encrypted and access requires authentication."),
        ],
    )
    gaps = analyze_design_gaps(feature)
    assert not any("security" in g.description.lower() for g in gaps)


def test_test_data_extraction_finds_quoted_and_hinted_fields():
    feature = make_feature(
        criteria=[
            AcceptanceCriterion(id="F1-AC1", text='A new task defaults to status "pending" with a title field.'),
        ],
    )
    reqs = analyze_test_data_requirements(feature)
    assert reqs[0].criterion_id == "F1-AC1"
    assert '"pending"' in reqs[0].data_fields
    assert "status" in reqs[0].data_fields
    assert "title" in reqs[0].data_fields


def test_test_data_missing_info_flags_no_example_value():
    feature = make_feature(
        criteria=[AcceptanceCriterion(id="F1-AC1", text="The due date must be a valid future date.")],
    )
    reqs = analyze_test_data_requirements(feature)
    assert any("format" in m.lower() or "example" in m.lower() for m in reqs[0].missing_info)


def test_test_data_ready_when_example_and_format_given():
    feature = make_feature(
        criteria=[
            AcceptanceCriterion(
                id="F1-AC1",
                text="The email field must match a valid format, e.g. user@example.com; invalid emails like 'not-an-email' are rejected.",
            )
        ],
    )
    reqs = analyze_test_data_requirements(feature)
    assert reqs[0].missing_info == []
    assert reqs[0].is_ready_for_test_case_generation


def test_run_gap_analysis_end_to_end():
    text = """# Task Creation

As a logged-in user, I want to create a task so that I can track my work.

### Acceptance Criteria

- AC-1: A task cannot be created without a title.
- AC-2: A newly created task defaults to status "pending".
"""
    features = parse_requirements_text(text)
    report = run_gap_analysis(features, requirements_source="inline")
    assert len(report.feature_analyses) == 1
    fa = report.feature_analyses[0]
    assert len(fa.test_data_requirements) == 2
    assert report.total_gap_count >= 0
    assert 0.0 <= report.overall_readiness_score <= 1.0
    assert report.document_level_design_gaps
