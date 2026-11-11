"""
Pure unit tests for the v1 scorer's sub-scores — no DB, no network, fast. These
are the tests to run constantly while iterating on scoring logic.
"""
from src.common.models import Posting
from src.scoring.formula_scorer import (
    location_fit_score,
    salary_fit_score,
    skill_match_score,
)


def make_posting(**overrides) -> Posting:
    defaults = dict(
        source="test",
        url="https://example.com/1",
        required_skills=None,
        salary_min=None,
        salary_max=None,
        remote_or_onsite=None,
        location=None,
    )
    defaults.update(overrides)
    return Posting(**defaults)


def test_skill_match_full_overlap():
    posting = make_posting(required_skills=["python", "docker"])
    score = skill_match_score(posting, ["Python", "Docker", "React"])
    assert score == 1.0


def test_skill_match_no_overlap():
    posting = make_posting(required_skills=["java", "spring"])
    score = skill_match_score(posting, ["python", "docker"])
    assert score == 0.0


def test_skill_match_unknown_requirements_scores_below_neutral():
    # Since 2026-08-14 (see skill_match_score): no extracted requirements read as uncertainty, not as a reward.
    posting = make_posting(required_skills=[])
    score = skill_match_score(posting, ["python"])
    assert score == 0.3


def test_skill_match_unknown_ranks_between_no_match_and_partial_match():
    unknown = skill_match_score(make_posting(required_skills=[]), ["python"])
    no_match = skill_match_score(make_posting(required_skills=["java", "php"]), ["python"])
    partial = skill_match_score(
        make_posting(required_skills=["python", "sql", "docker", "aws", "go"]), ["python", "sql"])
    assert no_match < unknown < partial


def test_salary_fit_no_floor_always_passes():
    posting = make_posting(salary_max=1)
    assert salary_fit_score(posting, preferred_min=0) == 1.0


def test_salary_fit_meets_floor():
    posting = make_posting(salary_max=120_000)
    assert salary_fit_score(posting, preferred_min=100_000) == 1.0


def test_salary_fit_below_floor_partial_credit():
    posting = make_posting(salary_max=50_000)
    score = salary_fit_score(posting, preferred_min=100_000)
    assert 0.0 < score < 1.0


def test_location_fit_remote_matches_remote_preference():
    posting = make_posting(remote_or_onsite="remote")
    assert location_fit_score(posting, preferred_location="Remote") == 1.0


def test_location_fit_onsite_mismatch():
    posting = make_posting(remote_or_onsite="onsite", location="Berlin")
    score = location_fit_score(posting, preferred_location="Remote")
    assert score < 1.0
