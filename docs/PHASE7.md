# Phase 7 — Weightage Scoring (Formula → Learned)

## What this phase is, in plain language

The end goal of this whole pipeline: take a big pile of scraped, structured,
classified postings and boil each one down to a single number — "how good a
fit is this for me" — so you can sort by it and look at the top of the list
first.

## What we built

- **`formula_scorer.py` (v1)** — three sub-scores (skill match, salary fit,
  location fit), each 0.0-1.0, combined by weights you set in
  `profile.yaml`. Transparent by design: you can explain this scorer's
  behavior in one sentence, and debug any surprising score by hand-checking
  three numbers.
- **`learned_scorer.py` (v2)** — once you've rated at least 15 postings
  1-5 by hand, a small Ridge regression model learns *your actual revealed
  preferences* from those ratings, instead of using the weights you guessed.
- **`main.py`** — always computes v1; automatically switches to v2 the moment
  a trained model exists, no config flag needed.

## Key concept: heuristic-first, learned-later

Shipping the formula first isn't a shortcut — it's the right engineering
order. A hardcoded, debuggable heuristic ships same-day and is *always*
explainable. A learned model needs real labeled data to be trustworthy at
all, and even then can behave in ways you can't fully predict from its
weights alone. Real internal tools follow exactly this maturity curve:
formula → collect real usage data → learn from it.

## Key concept: what the v2 model actually learns

It's not learning to read job postings from scratch — it's learning the
*relative importance* of the three sub-scores (plus skill count) against your
own hand-ratings. If you consistently rate postings with strong salary fit
highly even when the skill match is mediocre, Ridge regression will pick that
up and shift weight toward salary — something you might not have consciously
set that way in your v1 formula.

## Key concept: normalizing between scales

Your manual ratings are 1-5; v1's formula output is 0.0-1.0. `learned_scorer.py`
normalizes Ridge's raw prediction back into the 0-1 range so `fit_score` means
the same thing regardless of which version produced it — the rest of the
pipeline (Phase 8's report) never needs to know or care which scorer ran.
