"""
Shared TF-IDF feature extraction used by both the classifier and the clusterer.
Kept in one place so the two models are working off comparably-vectorized text
even though they're trained separately.
"""
from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer

DEFAULT_MAX_FEATURES = 800


def build_vectorizer(max_features: int = DEFAULT_MAX_FEATURES) -> TfidfVectorizer:
    return TfidfVectorizer(
        max_features=max_features,
        stop_words="english",
        ngram_range=(1, 2),  # unigrams + bigrams — "machine learning" as one signal
        min_df=2,
    )
