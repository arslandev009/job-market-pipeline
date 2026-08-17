# Phase 6 — Classical ML: Classification & Clustering

## What this phase is, in plain language

Two different ML tasks, often confused:

- **Classification (supervised)** — you decide the categories ahead of time
  (e.g. "frontend," "backend," "data/ml") and hand-label some examples; the
  model learns to sort new postings into *your* categories.
- **Clustering (unsupervised)** — no categories decided in advance, no labels
  needed; the algorithm finds whatever natural groupings exist in the data on
  its own. It might discover a grouping you never would've thought to define.

Both run on the same underlying feature representation (TF-IDF over the
posting text), but they answer different questions.

## What we built

- **`features.py`** — shared TF-IDF vectorization (unigrams + bigrams, so
  "machine learning" is captured as one signal, not two unrelated words).
- **`classify.py`** — a RandomForest classifier trained on whatever you've
  hand-labeled via `scripts/label_batch.py`. Includes 5-fold cross-validation
  so you get an honest accuracy estimate before trusting it on new data, and
  refuses to train at all below a minimum label count (better to say "not
  enough data yet" than silently produce garbage).
- **`cluster.py`** — KMeans clustering with `k` from Phase 4's elbow curve,
  plus a human-readable summary of each cluster's top TF-IDF terms (so you can
  eyeball "oh, cluster 2 is basically all senior backend roles").
- **`scripts/label_batch.py`** — the interactive tool that gets you from zero
  labels to a trainable dataset. There's no way around this step — every
  supervised model needs a human to create the ground truth once.

## Key concept: the cold-start problem

Day one, you have zero labels and zero trained models. This is normal and
universal in applied ML — the classifier gracefully no-ops with a clear log
message until you've labeled enough, and clustering (needing no labels at all)
works immediately as your first useful signal.

## Key concept: why not fully automate retraining

`src/ml/main.py` deliberately does *not* automatically retrain the classifier
on its own predictions. That's semi-supervised learning gone wrong if done
carelessly — the model's mistakes get fed back in as "truth" and compound over
time. Retraining here is a manual, deliberate step you trigger.
