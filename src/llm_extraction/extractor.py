"""
Calls a locally-hosted llama.cpp server, constrained by schema.gbnf, to turn each
posting's free-text into structured fields (seniority, remote/onsite, salary
range, location, required skills, and — as of 2026-08-16 — a candidate-fit
score judged directly by the model against the profile's skill list).

Why this design, in short (full reasoning in docs/ARCHITECTURE.md §5): the GBNF
grammar makes malformed JSON structurally impossible, so we don't need brittle
regex/retry-until-it-parses logic — if the server responds, the response parses.
We still wrap the HTTP call in retries (`tenacity`) because the *network* call
can fail even when the *grammar* can't.

CHANGE FROM v1 (run 2026-08-12 baseline: 38/200 unknown seniority, including
clear misses like "Chief Operating Officer" and "Administrative Assistant –
Entry Level"): the prompt now (a) gives an explicit title-vocabulary ladder
instead of a vague "use title cues" instruction, (b) includes few-shot examples
anchoring the exact failure modes we saw, and (c) the grammar/response now
carries a seniority_reasoning scratchpad field generated *before* the enum,
giving the model room to reason under constrained decoding instead of hedging
straight to "unknown". See docs/PROGRESS.md for the before/after comparison.

CHANGE 2026-08-16: replaced the hardcoded exact-string skill_match_score() in
src/scoring/formula_scorer.py with model judgment for postings that reach this
stage successfully. The old formula could only match "AI/ML" against a
posting's required_skills if the literal substring "ai/ml" appeared — it had
no way to recognize that "LLMs, NLP, embeddings" is the same domain. The model
already has the full posting text in context during extraction, so scoring
here costs zero extra LLM round-trips versus a separate scoring-stage call.
formula_scorer.py's compute_v1_score() remains as the fallback for any posting
where extraction fails outright or the model's fit_score comes back null — see
src/scoring/main.py's three-tier fallback (llm -> learned model -> v1 formula).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import get_settings
from src.common.logging import get_logger

logger = get_logger(__name__)

GRAMMAR_PATH = Path(__file__).parent / "schema.gbnf"

PROMPT_TEMPLATE = """You are extracting structured fields from a job posting.
Read the posting text and output ONLY the fields defined by the grammar — no
explanation outside the JSON fields themselves, no extra text.

Field-by-field rules:

1. seniority_reasoning — one short clause (under 15 words) naming the specific
   word or phrase in the TITLE that determines the level, e.g. "title contains
   Chief, C-suite role" or "title has no seniority qualifier, body gives no
   experience signal either". Write this BEFORE you decide the seniority value
   below — use it to think, not to restate the answer.

2. seniority — decide in this exact order, and STOP at the first rule that
   applies. Do not consider a later rule once an earlier one has matched —
   "no title qualifier" is NOT by itself a reason to say unknown; it's only
   the trigger to move on to the next rule.

   RULE A — title match. Check the title against this vocabulary ladder:
   - intern: Intern, Internship, Co-op, Trainee, Working Student
   - junior: Junior, Jr., Entry Level, Entry-Level, Associate, Assistant
     (when not paired with a C-level/VP/Director qualifier), Graduate
   - senior: Senior, Sr., Staff, Principal (individual-contributor track)
   - lead: Lead, Head of, Manager, Director, VP, President, Founder, or any
     "Chief * Officer" title (CEO, COO, CFO, CTO, CIO, CMO, etc. are all
     executive/lead-level regardless of which department they lead)
   If the title matches one of these, use it and stop — do not read further.

   RULE B — body match. If the title had no qualifier (e.g. "Backend
   Developer", "Loan Officer", "Data Analyst"), scan the body text for an
   explicit level signal: a stated years-of-experience requirement, "entry
   level"/"no experience necessary", or "must have senior-level expertise"
   type language. If found, use that level and stop.

   RULE C — default. If neither the title nor the body states a level, use
   "mid". This is the correct default for the large majority of ordinary job
   postings that simply don't spell out a seniority word — silence about
   level almost always means an unremarkable, standard-level role, not an
   unclassifiable one. Do NOT output unknown just because rules A and B
   didn't match.

   RULE D — unknown. Reserve this only for postings where the text itself is
   too short, generic, or garbled to tell what the role even is (e.g.
   placeholder/boilerplate text, a duplicate listing with no real content).
   This should be rare — noticeably rarer than "mid".

3. remote_or_onsite, salary_min, salary_max, location — use "unknown"/null if
   genuinely not stated; do not guess numeric values that aren't in the text.

4. required_skills — list at most 5 of the most important, specific skills —
   do not repeat the same skill or list generic filler (e.g. "teamwork",
   "communication" only count if the posting emphasizes them specifically).

5. fit_reasoning — one short clause (under 20 words) comparing this posting's
   actual skill/domain requirements against the CANDIDATE'S SKILLS listed
   below. Judge by domain and substance, not exact string overlap — e.g. a
   posting needing "LLMs, NLP, embeddings" IS a match for a candidate skill
   of "AI/ML" even though the words differ; a posting needing "React" is a
   reasonable partial match for a candidate skill of "Next.js"; a posting
   for a warehouse, hospitality, military, or other role with no realistic
   overlap to the candidate's skills is NOT a match regardless of how
   complete or well-written the posting is. Write this BEFORE you decide
   fit_score below — use it to think, not to restate the answer.

6. fit_score — a number from 0.0 to 1.0 rating how well this posting matches
   the candidate's actual skills, judged by domain relevance:
   - 0.8-1.0: core requirements are squarely in the candidate's skillset
   - 0.4-0.7: meaningful partial overlap — some required skills match, or
     the domain is adjacent (e.g. general software/data/AI role) even if
     the exact stack differs
   - 0.0-0.3: little to no realistic overlap — a different field entirely
   Base this on fit_reasoning, not on how complete the posting's other
   fields (salary, location) happen to be — an unrelated job with a listed
   salary is still a poor fit.

Candidate's skills: {candidate_skills}

Examples:
Title: "Chief Operating Officer" → seniority_reasoning: "title contains
Chief, C-suite executive role (Rule A)" → seniority: "lead"
Title: "Administrative Assistant – Entry Level" → seniority_reasoning: "title
says Entry Level, junior regardless of job family (Rule A)" →
seniority: "junior"
Title: "Backend Developer" (body has no experience-level language) →
seniority_reasoning: "no title or body signal, defaulting to standard
mid-level (Rule C)" → seniority: "mid"
Title: "Senior Data Analyst" → seniority_reasoning: "title contains Senior
(Rule A)" → seniority: "senior"
Title: "General Posting" (body: "See website for full details") →
seniority_reasoning: "text too generic to identify the role (Rule D)" →
seniority: "unknown"
Posting needs "NLP, LLMs, embeddings, ML" (candidate skills include "AI/ML")
→ fit_reasoning: "NLP/LLM/embeddings work is squarely the AI/ML domain" →
fit_score: 0.9
Posting needs "Docker, Kubernetes, CI/CD" (candidate skills include "Docker")
→ fit_reasoning: "Docker is an explicit candidate skill, direct overlap" →
fit_score: 0.7
Posting needs "Python, Databricks, DBT, Airflow" (candidate skills include
"Python") → fit_reasoning: "Python is an explicit candidate skill even
though the rest of the stack differs" → fit_score: 0.6
Posting needs "Gardener, Handyman, Driver" (candidate skills are software/AI)
→ fit_reasoning: "manual labor role, no overlap with software or AI skills"
→ fit_score: 0.05

Job posting text:
---
{posting_text}
---

JSON:"""


class ExtractionResult:
    def __init__(self, data: dict):
        # Kept (not discarded) rather than stripped after parsing — this is a
        # deliberate audit trail: for an assessment project, being able to show
        # *why* the model picked a seniority level (or a fit score) is worth
        # more than a clean dict. Downstream code (scoring, EDA) simply
        # ignores these reasoning fields when it doesn't need them.
        self.seniority_reasoning: str | None = data.get("seniority_reasoning")
        self.seniority: str = data.get("seniority", "unknown")
        self.remote_or_onsite: str = data.get("remote_or_onsite", "unknown")
        self.salary_min: int | None = data.get("salary_min")
        self.salary_max: int | None = data.get("salary_max")
        self.location: str | None = data.get("location")
        self.required_skills: list[str] = data.get("required_skills", [])
        self.fit_reasoning: str | None = data.get("fit_reasoning")
        self.fit_score: float | None = data.get("fit_score")


def _load_grammar() -> str:
    return GRAMMAR_PATH.read_text(encoding="utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _call_llm(prompt: str, grammar: str) -> str:
    settings = get_settings()
    url = f"{settings.llm_base_url.rstrip('/')}/completion"

    payload = {
        "prompt": prompt,
        "grammar": grammar,
        # Dropped 0.1 -> 0.0: fit_score is the one field where consistency
        # matters more than any variety benefit temperature might give —
        # the same posting text should score the same way every run.
        "temperature": 0.0,
        # Bumped 600 -> 700 -> 780: the seniority_reasoning field and now the
        # fit_reasoning + fit_score fields each add a small number of tokens
        # per response, and we don't want either scratchpad field to eat into
        # the budget the tail fields (required_skills, fit_score) need.
        "n_predict": 780,
        "stop": ["\n---"],
    }

    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        return body.get("content", "")


def extract_fields(posting_text: str, candidate_skills: list[str]) -> ExtractionResult | None:
    if not posting_text or not posting_text.strip():
        return None

    # Cap input length — local 7B-9B-class models have limited context, and we
    # only need the first ~4000 chars to get title/company/requirements in
    # practice.
    truncated = posting_text[:4000]
    skills_str = ", ".join(candidate_skills) if candidate_skills else "(none specified)"
    prompt = PROMPT_TEMPLATE.format(posting_text=truncated, candidate_skills=skills_str)
    grammar = _load_grammar()

    try:
        raw_output = _call_llm(prompt, grammar)
        # Defense-in-depth (2026-08-16): strip any stray raw control
        # characters before parsing, even though the grammar itself now
        # excludes them (see schema.gbnf). Belt-and-suspenders — if some
        # edge case ever slips a literal control byte through anyway, this
        # keeps that one posting from failing extraction outright instead
        # of silently relying on the grammar being perfect.
        import re

        sanitized = re.sub(r"[\x00-\x1f]", "", raw_output)
        data = json.loads(sanitized)
        return ExtractionResult(data)
    except httpx.HTTPError as exc:
        logger.error("llm_call_failed", error=str(exc))
        return None
    except json.JSONDecodeError as exc:
        # Should be rare given the grammar constraint — logged loudly if it ever
        # happens since it means the grammar and the model disagree somehow.
        logger.error("llm_output_not_valid_json", error=str(exc), raw_output=raw_output[:500])
        return None
