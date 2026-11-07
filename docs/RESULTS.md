# Classifier evaluation (M2)

Generated 2026-11-07 by `scripts/evaluate_classifier.py`. Every number below comes from that run.

## What was evaluated

- **252 English job postings** in 7 hand-defined categories (`customer_support_admin`, `data_ai_ml`, `devops_cloud_security`, `management_finance_hr`, `other`, `sales_marketing`, `software_engineering`).
- **Labels: 26 by hand (gold), 226 by a local LLM (Qwen3.5-9B, silver).** Scores measured against the silver labels show how well the classifier reproduces the LLM's labels, not how well it matches the truth. How often the LLM label is wrong has not been measured on a large enough sample yet.
- Class counts: software_engineering 68, management_finance_hr 57, sales_marketing 46, devops_cloud_security 26, data_ai_ml 20, other 19, customer_support_admin 16.

## Method

- Repeated stratified group k-fold: 5 folds x 5 repeats (different shuffles). The table shows mean ± std over the repeats; each repeat scores every posting once, with a model that never saw it.
- The TF-IDF vectorizer is inside the pipeline, so it is fitted on the training folds only.
- 8 postings were near-duplicates of another one (cosine >= 0.9); duplicates are kept in the same fold and never split across train and test.
- No hyperparameter tuning and no separate untouched test set: this is a cross-validation estimate.

## Results

| model | accuracy | macro-F1 | accuracy on hand-labelled rows (n=26) | accuracy on LLM-labelled rows |
|---|---|---|---|---|
| baseline: most frequent class | 0.261 ± 0.017 | 0.064 ± 0.007 | 0.177 ± 0.046 | 0.271 ± 0.025 |
| logistic regression (TF-IDF) | 0.578 ± 0.011 | 0.550 ± 0.018 | 0.754 ± 0.031 | 0.558 ± 0.013 |
| random forest (current model) | 0.556 ± 0.007 | 0.391 ± 0.005 | 0.708 ± 0.019 | 0.539 ± 0.009 |

Accuracy of always guessing the most frequent class: 0.270. Macro-F1 averages the classes equally, so a model that ignores small classes scores low on it.

## Per class (logistic regression (TF-IDF), first repeat)

| class | precision | recall | F1 | postings |
|---|---|---|---|---|
| customer_support_admin | 0.60 | 0.56 | 0.58 | 16 |
| data_ai_ml | 0.44 | 0.55 | 0.49 | 20 |
| devops_cloud_security | 0.39 | 0.73 | 0.51 | 26 |
| management_finance_hr | 0.67 | 0.65 | 0.66 | 57 |
| other | 0.30 | 0.37 | 0.33 | 19 |
| sales_marketing | 0.84 | 0.78 | 0.81 | 46 |
| software_engineering | 0.71 | 0.44 | 0.55 | 68 |

## Confusion matrix (rows = label, columns = prediction, first repeat)

| label \ predicted | customer_support_admin | data_ai_ml | devops_cloud_security | management_finance_hr | other | sales_marketing | software_engineering |
|---|---|---|---|---|---|---|---|
| customer_support_admin | 9 | 0 | 1 | 2 | 1 | 3 | 0 |
| data_ai_ml | 0 | 11 | 2 | 0 | 3 | 0 | 4 |
| devops_cloud_security | 1 | 0 | 19 | 4 | 0 | 0 | 2 |
| management_finance_hr | 3 | 2 | 8 | 37 | 4 | 2 | 1 |
| other | 0 | 2 | 0 | 6 | 7 | 0 | 4 |
| sales_marketing | 1 | 0 | 5 | 3 | 0 | 36 | 1 |
| software_engineering | 1 | 10 | 14 | 3 | 8 | 2 | 30 |

## Leakage control

Random forest with the labels **shuffled**: macro-F1 0.125 ± 0.011 (the real labels give 0.391 ± 0.005). A score close to chance after shuffling means the pipeline learns from the labels and does not leak them through the folds.

## Limitations

- Small data set (a few hundred postings from one scrape of two job APIs), so differences of a few points between models are inside the noise (see the ± values).
- Most labels come from an LLM that makes mistakes of its own, for example on borderline roles such as account managers, product managers and designers.
- The categories were defined by hand for this data; roles that fit none of them end up in `other`.
- Only English postings are used.
