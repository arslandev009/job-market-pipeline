"""
v1 scorer: a transparent, hand-weighted formula over three sub-scores, each
0.0-1.0, combined per the weights in config/profile.yaml. This is deliberately
the *first* thing built — debuggable, explainable in one sentence to anyone,
and a real baseline to compare Phase 7 v2's learned model against later (see
docs/ARCHITECTURE.md §7 for why a two-stage scorer at all).
"""
from __future__ import annotations

from src.common.config import Profile
from src.common.models import Posting


def skill_match_score(posting: Posting, candidate_skills: list[str]) -> float:
    required = [s.lower() for s in (posting.required_skills or [])]
    if not required:
        # CHANGED 2026-08-14: was 0.5 (neutral). At 0.5, postings with NO
        # extracted skill requirements outranked postings with a genuine,
        # partial skill match — e.g. needing 5 skills with 2 matched scored
        # 0.4, LOSING to a posting about which nothing at all is known.
        # That's backwards: missing data should read as uncertainty, not as
        # a reward. 0.3 keeps real partial matches (most postings need 3-5
        # skills, so even 1 match lands at 0.2-0.33) competitive with or
        # ahead of unknown data, while a posting whose EXPLICIT requirements
        # you fully lack (matched=0) still correctly scores 0.0 — that's a
        # real negative signal and should stay worse than "we don't know."
        return 0.3
    owned = {s.lower() for s in candidate_skills}
    matched = sum(1 for skill in required if skill in owned)
    return min(1.0, matched / len(required))


def salary_fit_score(posting: Posting, preferred_min: float) -> float:
    if preferred_min <= 0:
        return 1.0  # no floor set — everything passes
    if posting.salary_max is not None:
        if posting.salary_max >= preferred_min:
            return 1.0
        # Partial credit the closer the max offer is to the floor, not a hard 0.
        return max(0.0, posting.salary_max / preferred_min)
    if posting.salary_min is not None:
        return 1.0 if posting.salary_min >= preferred_min else 0.5
    return 0.5  # salary wasn't extracted — neutral, don't punish missing data


def location_fit_score(posting: Posting, preferred_location: str) -> float:
    preferred = preferred_location.strip().lower()
    remote_pref = preferred in ("remote", "anywhere", "any")

    if posting.remote_or_onsite == "remote" and remote_pref:
        return 1.0
    if posting.remote_or_onsite == "remote":
        return 0.8  # remote is broadly good even if you technically wanted a location
    if posting.location and preferred in posting.location.lower():
        return 1.0
    if posting.remote_or_onsite in (None, "unknown") and not posting.location:
        return 0.5  # unknown — neutral
    return 0.3


def compute_v1_score(posting: Posting, profile: Profile) -> float:
    skill = skill_match_score(posting, profile.candidate.skills)
    salary = salary_fit_score(posting, profile.candidate.preferred_salary_min)
    location = location_fit_score(posting, profile.candidate.preferred_location)

    w = profile.scoring.weights
    return round(
        skill * w.skill_match + salary * w.salary_fit + location * w.location_fit, 4
    )