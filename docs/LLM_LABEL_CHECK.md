# LLM label check

Generated 2026-11-07 by `scripts/llm_vs_gold.py`.

Question: how often does the local LLM labeller (Qwen3.5-9B, the one that labelled most postings) pick a different category than the hand label?

- Hand-labelled postings checked: **18** (8 left out because their titles are examples inside the prompt).
- LLM agrees with the hand label on **14 of 18** = **78%**
  (95% confidence interval 55% to 91%: with so few postings the real rate could be anywhere in that range).

## Disagreements

| id | title | hand label | LLM label |
|---|---|---|---|
| 5 | Software Engineer Infrastructure | software_engineering | devops_cloud_security |
| 9 | Partner Operations Manager | management_finance_hr | customer_support_admin |
| 14 | Country Manager Canada | management_finance_hr | sales_marketing |
| 21 | Solutions Engineer | sales_marketing | devops_cloud_security |

## How to read this

- A disagreement does not prove the LLM is wrong: the hand label is one person's opinion and several roles sit on the border between two categories.
- These postings are the first ones in the database, not a random sample, and the hand labels contain mostly non-technical roles.
- With this few postings the number is a rough guide only. Checking 40 more LLM-labelled postings by hand would narrow the interval a lot.
