# What This Project Actually Does — Plain English Guide

No jargon. If a technical word shows up, it's explained right where it's used.

---

## 1. The one-sentence version

You built a system that goes out to job websites, pulls in job postings, reads
each one, figures out useful facts about it (what skills it needs, how senior
it is, where it's based, does it pay well), decides how good a match it is
for YOU specifically, and puts the good matches in a spreadsheet you can
check — all without you reading a single job posting yourself.

---

## 2. The big picture — five stages, one after another

```
1. SCRAPE   →   2. EXTRACT   →   3. CLASSIFY/CLUSTER   →   4. SCORE   →   5. REPORT
(get raw        (read each         (sort into groups,        (rate how       (write the
 job posts)      posting, pull      filter out junk)           good a         good ones
                 out facts)                                    match it is)   to a Sheet)
```

Each stage reads what the previous stage produced, does its job, and hands
off to the next one. Nothing runs out of order — each stage waits for the
one before it to finish before starting (that's what all the Docker
"depends_on" settings are for).

---

## 3. Stage 1 — Scraping (getting the raw data)

**What happens:** The system asks two job websites (RemoteOK and Arbeitnow)
for their current job listings, using each site's own public API — think of
an API as a website's "give me your data directly, in a structured format"
door, instead of you having to visually read the webpage.

**Is this AI?** No. Zero AI involved. This is plain code: "go ask this
website for its job list, save what comes back." No judgment calls are made
here — every posting that comes back gets saved, no filtering yet.

**One control you added:** `SCRAPER_MAX_PER_SOURCE` — a simple cap so you can
say "only keep the first 25 from each site" for a fast test, instead of
waiting on hundreds every time.

---

## 4. Stage 2 — Extraction (reading each posting and pulling out facts)

**This is where the AI model actually does real work.** You're running a
local AI model called **Qwen 9B** (9 billion parameters — think of that
as roughly "how much this specific model was trained to understand
language and reasoning," a mid-sized model that runs entirely on your own
graphics card, not in the cloud). It runs via a program called
`llama-server.exe`, which is just the engine that lets you send text to the
model and get a response back, over your own computer's network, nothing
leaves your machine.

**What you actually ask the model to do, in plain terms:** For every single
job posting's raw text, you send it a prompt (a written instruction) that
says, roughly:

> "Here's a job posting. Tell me: how senior is this role, is it remote or
> in-office, what's the salary range if mentioned, where is it located, and
> what are the top 5 skills it needs. Also — here's a list of MY skills —
> tell me how good a match this job is for me, and explain your reasoning
> before giving me a number."

The model reads the posting and genuinely reasons through it — it's not
looking up answers from a table, it's using its trained understanding of
language to figure out, for example, that "Chief Operating Officer" is a
senior/executive title even though the word "senior" never appears in the
posting.

**The one hard rule enforced here (not the model's choice):** the model is
forced to answer in a strict, fixed format — always the same fields, in the
same order, as valid data (a number is really a number, not "N/A" typed into
a number field). This is done through something called a "grammar" — think
of it as a rigid form the model has to fill in, one field at a time, and it
literally cannot type anything outside the fields on the form. **This
grammar controls the SHAPE of the answer, not the CONTENT.** The model still
decides everything about what actually goes in each field — the grammar
just guarantees you'll never get broken/unreadable output.

**Two extra tricks used to make the model's answers more accurate:**

1. **"Think out loud before answering."** For both seniority level and the
   fit score, the model is told to write a short one-sentence explanation
   FIRST, then give its final answer. This isn't just for your benefit — it
   noticeably improves the model's own accuracy, because it gives the model
   room to reason instead of being forced to blurt out an answer with zero
   space to think.
2. **Examples baked into the instructions.** The prompt includes several
   worked examples ("if the title is X, the answer should be Y") so the
   model has a clear pattern to follow instead of guessing at what you want.

**Is this AI or hardcoded rules?** This stage is genuinely AI judgment. The
model is making real decisions based on understanding the text — nothing
here is a simple "if the word 'senior' appears, mark it senior" rule. That
kind of literal rule only shows up later (see Stage 4).

---

## 5. Stage 3 — Classify & Cluster (sorting into groups, filtering junk)

**Important distinction:** this stage does NOT use the big language model at
all. This is a completely different, much simpler kind of technology called
**"classical machine learning"** — smaller, faster, purely statistical
methods that don't "understand" language the way the LLM does, they just
find patterns in word frequency.

**What happens here, in plain terms:**

- **Language filter** — postings that aren't in English get dropped from
  further consideration (not deleted, just marked out-of-scope). This uses
  a simple language-detection library, not the AI model.
- **Clustering** — postings get grouped into a handful of buckets based on
  which words tend to appear together (e.g. one cluster ends up full of
  "team, security, javascript" postings, another full of "training, health,
  infantry" postings). This is done with a classical statistical method
  (counting word patterns, not reading for meaning), so it's fast and cheap
  but has no real understanding — it just notices "these documents use
  similar words."
- **Category labeling** — each posting gets tagged into a broad bucket like
  `tech_product`, `admin_support`, `customer_retail`, or `other`.

**Is this AI?** Technically yes, it's "machine learning," but it's a
fundamentally different, much dumber kind than the language model in Stage
2. It has no reasoning ability — it's counting and grouping, not
understanding meaning.

---

## 6. Stage 4 — Scoring (deciding how good a match each job is)

This is the most interesting stage because it actually **combines both
approaches** — genuine AI judgment AND old-fashioned hardcoded rules,
deliberately, as a safety net for each other. Here's exactly how:

### The hardcoded rule-based score (called "v1")
This is a formula, written entirely in plain code, with zero AI involved.
It looks at three things and adds them up with fixed weights:
- **Does the posting's list of required skills contain any of YOUR skills,
  word for word?** (exact text matching — "Docker" only counts if the
  posting literally says "Docker")
- **Does the salary meet your minimum?**
- **Does the location/remote setup match what you want?**

This is 100% predictable and explainable — you could recalculate it by hand
with a calculator. Its weakness: it can only catch matches that use the
exact same words. It has no idea that "NLP" and "AI/ML" are related.

### The AI-judged score (from Stage 2's extraction call)
This is the model reading the posting and your skill list together and
using its actual understanding of the world to judge relevance — it
correctly recognizes that a posting needing "LLMs, embeddings, NLP" is a
strong match for someone who listed "AI/ML" as a skill, even though none of
those exact words overlap. This is real reasoning, not string-matching.

### Why you use BOTH together
Early testing showed the AI-judged score, while smarter, wasn't perfectly
consistent — a couple of postings that had an EXACT, obvious skill match
("Docker" appearing word-for-word in both the posting and your skill list)
still got scored as a 0 by the AI, purely due to normal AI variability.

The fix: **take whichever of the two scores is HIGHER, for every posting.**
This means:
- If the AI catches a smart match the hardcoded rule would've missed →
  the AI's higher score wins.
- If the AI has an off moment and undersells an obvious literal match →
  the hardcoded rule's score rescues it.

Neither system can pull a score DOWN, only up — so you get the best of both:
the AI's intelligence when it works well, and a dumb-but-reliable backup
when it doesn't.

**Bottom line: you are NOT running on pure AI judgment alone, and you're NOT
running on pure hardcoded rules alone. It's deliberately both, combined as a
safety net.**

---

## 7. Stage 5 — Reporting (writing the final results to Google Sheets)

**What happens:** Once every posting has a final score, the system takes
all of them, sorts by score (best matches first), and writes them as rows
into a Google Sheet you already have set up.

**Is this AI?** No. Pure code — connect to Google's API, write the rows,
done. No decisions are made here; everything decision-related already
happened in the earlier stages.

---

## 8. The dashboard (Streamlit) — the part you click buttons on

This is a separate piece that sits ON TOP of everything above — it doesn't
change what any stage does, it just gives you a visual way to trigger stages
and look at the data, instead of typing commands into a terminal every time.

**What it actually does, technically:** it's a small Python web app that
runs on your own computer (not in Docker, not on the internet — just a local
webpage only you can see). When you click "Run Full Pipeline," it does
exactly the same thing as you typing `docker compose up --build` into
PowerShell — it just does it for you and shows the output live on the page
instead of in a terminal window.

**The data-browsing tabs** (Raw Scraped Data, Extraction Before/After, Final
Results) work by directly querying the same database (Postgres) that every
stage above reads and writes to. It's a window into the same data, not a
separate copy.

**Is this AI?** No. Zero AI here either — it's a display and control layer.

---

## 9. Where does Docker fit into all this?

Docker is just a way of packaging each stage (scraper, extractor, ml,
scorer, sheets-writer) into its own isolated little box, so each one has
exactly the software it needs without conflicting with anything else on
your computer. `docker compose up` starts all five boxes in the correct
order, waiting for each one to finish before starting the next. It's
plumbing, not intelligence — it doesn't make any decisions about your data.

---

## 10. So, to directly answer: AI or hardcoded rules?

| Stage | AI or hardcoded? | Details |
|---|---|---|
| Scraping | Hardcoded | Just calling website APIs, no judgment |
| Cleaning/dedup | Hardcoded | Pattern/rule-based text cleanup |
| Extraction (seniority, salary, location, skills) | **AI (real reasoning)** | The 9B model genuinely reads and interprets each posting |
| Fit scoring (the AI half) | **AI (real reasoning)** | Same model, same call, judging your-skills-vs-posting |
| Fit scoring (the v1 half) | Hardcoded | Plain word-matching formula, zero AI |
| Final fit score you see | **Hybrid** | Takes the higher of the AI's score and the hardcoded formula's score |
| Clustering/categorization | Classical ML (not the LLM) | Statistical word-pattern grouping, no real understanding |
| Google Sheets writing | Hardcoded | Just pushes final data, no decisions |
| Dashboard | Hardcoded | Pure display + button-triggered commands |

The genuinely intelligent part of this whole system is concentrated in one
place: the single call to the 9B model during extraction, which is doing
two jobs at once (pulling out structured facts, and judging fit against your
skills) in the same pass, so it costs you no extra time or model calls
beyond what you'd already need for extraction alone.