# Classifier evaluation (M2)

Generated 2026-11-07 by `scripts/evaluate_classifier.py`. Every number below comes from that run.

## What was evaluated

- **252 English job postings** in 7 hand-defined categories (`customer_support_admin`, `data_ai_ml`, `devops_cloud_security`, `management_finance_hr`, `other`, `sales_marketing`, `software_engineering`).
- **Labels: 26 by hand (gold), 226 by a local LLM (Qwen3.5-9B, silver).** Scores measured against the silver labels show how well the classifier reproduces the LLM's labels, not how well it matches the truth. On 18 hand-labelled postings the LLM chose the same category as the hand label 14 times (78%, 95% interval 55% to 91%); see `docs/LLM_LABEL_CHECK.md`.
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
| logistic regression C=1, 800 features | 0.578 ± 0.011 | 0.550 ± 0.018 | 0.754 ± 0.031 | 0.558 ± 0.013 |
| logistic regression C=3, 800 features | 0.601 ± 0.020 | 0.560 ± 0.028 | 0.785 ± 0.039 | 0.580 ± 0.023 |
| logistic regression C=10, 800 features | 0.611 ± 0.008 | 0.558 ± 0.017 | 0.792 ± 0.052 | 0.590 ± 0.011 |
| logistic regression C=3, 3000 features | 0.597 ± 0.016 | 0.532 ± 0.017 | 0.846 ± 0.024 | 0.568 ± 0.019 |
| random forest (current model) | 0.556 ± 0.007 | 0.391 ± 0.005 | 0.708 ± 0.019 | 0.539 ± 0.009 |

The best configuration (**logistic regression C=3, 800 features**) was picked by macro-F1 on this same cross-validation, so its score is slightly optimistic. All settings were fixed in advance; nothing was tuned on a test fold.

Accuracy of always guessing the most frequent class: 0.270. Macro-F1 averages the classes equally, so a model that ignores small classes scores low on it.

## Per class (logistic regression C=3, 800 features, first repeat)

| class | precision | recall | F1 | postings |
|---|---|---|---|---|
| customer_support_admin | 0.60 | 0.56 | 0.58 | 16 |
| data_ai_ml | 0.48 | 0.50 | 0.49 | 20 |
| devops_cloud_security | 0.42 | 0.69 | 0.52 | 26 |
| management_finance_hr | 0.68 | 0.67 | 0.67 | 57 |
| other | 0.39 | 0.37 | 0.38 | 19 |
| sales_marketing | 0.83 | 0.76 | 0.80 | 46 |
| software_engineering | 0.72 | 0.60 | 0.66 | 68 |

## Confusion matrix (rows = label, columns = prediction, first repeat)

| label \ predicted | customer_support_admin | data_ai_ml | devops_cloud_security | management_finance_hr | other | sales_marketing | software_engineering |
|---|---|---|---|---|---|---|---|
| customer_support_admin | 9 | 0 | 1 | 3 | 0 | 3 | 0 |
| data_ai_ml | 0 | 10 | 2 | 0 | 3 | 0 | 5 |
| devops_cloud_security | 1 | 1 | 18 | 4 | 0 | 0 | 2 |
| management_finance_hr | 3 | 2 | 7 | 38 | 3 | 2 | 2 |
| other | 0 | 2 | 0 | 5 | 7 | 0 | 5 |
| sales_marketing | 1 | 0 | 4 | 4 | 0 | 35 | 2 |
| software_engineering | 1 | 6 | 11 | 2 | 5 | 2 | 41 |

## Leakage control

logistic regression C=3, 800 features with the labels **shuffled**: macro-F1 0.160 ± 0.036 (the real labels give 0.560 ± 0.028; guessing among 7 classes gives about 0.14). A score close to chance after shuffling means the pipeline learns from the labels and does not leak them through the folds.

## Limitations

- Small data set (a few hundred postings from one scrape of two job APIs), so differences of a few points between models are inside the noise (see the ± values).
- Most labels come from an LLM that makes mistakes of its own, for example on borderline roles such as account managers, product managers and designers.
- The categories were defined by hand for this data; roles that fit none of them end up in `other`.
- Only English postings are used.
