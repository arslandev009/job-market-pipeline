import textwrap

import pytest

from src.common.config import Profile


def test_profile_load_valid_yaml(tmp_path):
    content = textwrap.dedent("""
        candidate:
          skills: ["Python", "Docker"]
          preferred_salary_min: 80000
          preferred_location: "Remote"
        scoring:
          weights:
            skill_match: 0.6
            salary_fit: 0.2
            location_fit: 0.2
        sources:
          enabled: ["remoteok"]
    """)
    path = tmp_path / "profile.yaml"
    path.write_text(content)

    profile = Profile.load(path)
    assert profile.candidate.skills == ["Python", "Docker"]
    assert profile.scoring.weights.skill_match == 0.6
    assert profile.sources.enabled == ["remoteok"]


def test_profile_missing_file_raises_helpful_error(tmp_path):
    missing = tmp_path / "profile.yaml"
    with pytest.raises(FileNotFoundError, match="profile.example.yaml"):
        Profile.load(missing)


def test_profile_defaults_when_sections_omitted(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("candidate:\n  skills: []\n")
    profile = Profile.load(path)
    # scoring/sources sections weren't provided — defaults should kick in
    assert profile.scoring.weights.skill_match == 0.5
    assert "remoteok" in profile.sources.enabled
