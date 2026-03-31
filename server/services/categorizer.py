"""Transaction categorizer — rule-based keyword matching + ML fallback.

Categorization priority:
  1. Income detection (salary, refund, interest) for credit transactions
  2. Rule-based keyword matching with weighted scoring
  3. ML fallback (TF-IDF + Logistic Regression) with confidence threshold
  4. Fallback → "Uncategorized"

The ML model is bootstrapped from synthetic training data generated from
CATEGORY_RULES keywords, then incrementally improved as users confirm
or correct categorizations.
"""
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from server.utils.constants import CATEGORY_RULES, MERCHANT_KEYWORDS
from server.config import ML_MODEL_PATH

logger = logging.getLogger(__name__)

# ── Synthetic training phrases per category (used to bootstrap ML model) ──
# Each keyword from CATEGORY_RULES is expanded into mini-phrases so the
# TF-IDF vectorizer has realistic n-gram context to learn from.
_PHRASE_TEMPLATES = [
    "{kw}",
    "payment to {kw}",
    "upi {kw}",
    "{kw} purchase",
    "{kw} payment",
    "pos {kw}",
    "{kw} online",
    "paid {kw}",
    "{kw} services",
    "bill {kw}",
]


class TransactionCategorizer:
    """Categorize transactions using keyword rules + ML (TF-IDF + LogReg)."""

    def __init__(self, auto_bootstrap: bool = True):
        self.ml_model: Optional[Pipeline] = None
        self._load_model()

        # If no saved model exists, bootstrap from synthetic data
        if self.ml_model is None and auto_bootstrap:
            self._bootstrap_model()

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def categorize(
        self,
        description: str,
        amount: float = 0,
        txn_type: str = "",
        merchant_clean: str = "",
    ) -> str:
        """Categorize a single transaction.

        Priority: income → keyword rules → ML → "Uncategorized"
        """
        desc_lower = description.lower().strip()
        merchant_lower = merchant_clean.lower().strip() if merchant_clean else ""

        # ── 1. Income / credit detection ────────────────────────────
        if txn_type == "credit":
            income_cat = self._check_income(desc_lower)
            if income_cat:
                return income_cat

        # ── 2. Rule-based keyword matching (weighted) ───────────────
        rule_match = self._rule_based(desc_lower, merchant_lower)
        if rule_match:
            return rule_match

        # ── 3. ML fallback ──────────────────────────────────────────
        ml_result = self._ml_predict(desc_lower, merchant_lower)
        if ml_result:
            return ml_result

        return "Uncategorized"

    def categorize_batch(self, transactions: list[dict]) -> list[dict]:
        """Categorize a list of transaction dicts in-place."""
        for txn in transactions:
            desc = txn.get("description", "") or txn.get("raw_description", "")
            txn["category"] = self.categorize(
                description=desc,
                amount=txn.get("amount", 0),
                txn_type=txn.get("transaction_type", ""),
                merchant_clean=txn.get("merchant_clean", ""),
            )
        return transactions

    # ────────────────────────────────────────────────────────────────
    # Income detection
    # ────────────────────────────────────────────────────────────────

    _SALARY_KW = [
        "salary", "payroll", "wage", "stipend", "income",
        "pension", "bonus", "commission", "honorarium",
    ]
    _REFUND_KW = ["refund", "reversal", "cashback", "reward", "return"]
    _INTEREST_KW = ["interest", "int.cr", "int cr", "dividend", "int credit"]

    def _check_income(self, desc: str) -> Optional[str]:
        for kw in self._SALARY_KW:
            if kw in desc:
                return "Salary"
        for kw in self._REFUND_KW:
            if kw in desc:
                return "Refund"
        for kw in self._INTEREST_KW:
            if kw in desc:
                return "Interest"
        return None

    # ────────────────────────────────────────────────────────────────
    # Rule-based keyword matching (weighted scoring)
    # ────────────────────────────────────────────────────────────────

    def _rule_based(self, desc: str, merchant: str) -> Optional[str]:
        """Match against CATEGORY_RULES with weighted scoring.

        Scoring:
        • Base score = keyword length  (longer keywords are more specific)
        • +5 bonus if keyword matches merchant_clean (higher signal)
        • +3 bonus for multi-word keyword match (phrase match)
        """
        best_match = None
        best_score = 0

        # Combine desc and merchant for matching
        combined = f"{desc} {merchant}".lower()

        for category, keywords in CATEGORY_RULES.items():
            for keyword in keywords:
                if keyword in combined:
                    score = len(keyword)

                    # Bonus: keyword found in cleaned merchant name
                    if merchant and keyword in merchant:
                        score += 5

                    # Bonus: multi-word keyword (more specific)
                    if " " in keyword:
                        score += 3

                    if score > best_score:
                        best_score = score
                        best_match = category

        return best_match

    # ────────────────────────────────────────────────────────────────
    # ML prediction (TF-IDF + Logistic Regression)
    # ────────────────────────────────────────────────────────────────

    def _ml_predict(self, desc: str, merchant: str) -> Optional[str]:
        """Use the ML model to predict category."""
        if self.ml_model is None:
            return None

        text = f"{desc} {merchant}".strip()
        if not text:
            return None

        try:
            prediction = self.ml_model.predict([text])[0]
            probabilities = self.ml_model.predict_proba([text])[0]
            max_prob = float(max(probabilities))

            # Only trust confident predictions (> 40%)
            if max_prob > 0.40:
                logger.debug(
                    "ML categorized '%s' → '%s' (%.0f%%)",
                    text[:40], prediction, max_prob * 100,
                )
                return prediction
        except Exception as e:
            logger.warning("ML categorization failed: %s", e)

        return None

    # ────────────────────────────────────────────────────────────────
    # Model loading / saving
    # ────────────────────────────────────────────────────────────────

    def _load_model(self):
        """Load a pre-trained model from disk if available."""
        model_path = ML_MODEL_PATH / "categorizer_lr.pkl"
        if model_path.exists():
            try:
                with open(model_path, "rb") as f:
                    self.ml_model = pickle.load(f)
                logger.info("Loaded ML categorization model (LogisticRegression)")
            except Exception as e:
                logger.warning("Failed to load ML model: %s", e)
                self.ml_model = None

    def _save_model(self):
        """Persist the current model to disk."""
        ML_MODEL_PATH.mkdir(parents=True, exist_ok=True)
        model_path = ML_MODEL_PATH / "categorizer_lr.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(self.ml_model, f)
        logger.info("Saved ML categorization model to %s", model_path)

    # ────────────────────────────────────────────────────────────────
    # Bootstrap: generate synthetic training data from keyword rules
    # ────────────────────────────────────────────────────────────────

    def _bootstrap_model(self):
        """Build an initial model from CATEGORY_RULES + MERCHANT_KEYWORDS.

        Creates synthetic training phrases so the model can generalize
        to descriptions that don't exactly match any keyword.
        """
        descriptions: list[str] = []
        labels: list[str] = []

        # From CATEGORY_RULES keywords
        for category, keywords in CATEGORY_RULES.items():
            for kw in keywords:
                for template in _PHRASE_TEMPLATES:
                    descriptions.append(template.format(kw=kw))
                    labels.append(category)

        # From MERCHANT_KEYWORDS → infer category via CATEGORY_RULES
        for merchant_key, merchant_display in MERCHANT_KEYWORDS.items():
            cat = self._infer_category_for_merchant(merchant_key)
            if cat:
                for template in _PHRASE_TEMPLATES[:5]:  # fewer per merchant
                    descriptions.append(template.format(kw=merchant_key))
                    labels.append(cat)
                    descriptions.append(template.format(kw=merchant_display.lower()))
                    labels.append(cat)

        if len(descriptions) < 20:
            logger.warning("Not enough synthetic data to bootstrap ML model")
            return

        self.train(descriptions, labels)
        logger.info(
            "Bootstrapped ML model from %d synthetic samples (%d categories)",
            len(descriptions),
            len(set(labels)),
        )

    def _infer_category_for_merchant(self, merchant_key: str) -> Optional[str]:
        """Look up which category a merchant keyword falls into."""
        for category, keywords in CATEGORY_RULES.items():
            for kw in keywords:
                if kw in merchant_key or merchant_key in kw:
                    return category
        return None

    # ────────────────────────────────────────────────────────────────
    # Training (TF-IDF + Logistic Regression)
    # ────────────────────────────────────────────────────────────────

    def train(self, descriptions: list[str], categories: list[str]):
        """Train (or retrain) the ML model.

        Uses TF-IDF on uni+bi-grams → Logistic Regression with
        class-weighted balancing for imbalanced categories.

        Call with user-confirmed corrections to improve over time.
        """
        if len(descriptions) < 10:
            logger.warning("Need at least 10 samples to train")
            return

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=8000,
                ngram_range=(1, 2),
                sublinear_tf=True,        # dampens high-frequency terms
                min_df=1,
                max_df=0.95,
                strip_accents="unicode",
            )),
            ("clf", LogisticRegression(
                C=5.0,                     # moderate regularization
                max_iter=1000,
                class_weight="balanced",   # handles imbalanced categories
                solver="lbfgs",
            )),
        ])

        pipeline.fit(descriptions, categories)
        self.ml_model = pipeline
        self._save_model()
        logger.info("Trained ML model with %d samples", len(descriptions))

    def retrain_incremental(
        self,
        new_descriptions: list[str],
        new_categories: list[str],
    ):
        """Add new labelled data and retrain.

        Merges with existing synthetic data for a full refit.
        Future improvement: use partial_fit with SGDClassifier.
        """
        # Re-generate synthetic base
        descriptions: list[str] = []
        labels: list[str] = []
        for category, keywords in CATEGORY_RULES.items():
            for kw in keywords:
                for template in _PHRASE_TEMPLATES[:3]:  # lighter base
                    descriptions.append(template.format(kw=kw))
                    labels.append(category)

        # Append user-corrected data (weighted more by repetition)
        for desc, cat in zip(new_descriptions, new_categories):
            for _ in range(3):  # repeat to increase user-data weight
                descriptions.append(desc)
                labels.append(cat)

        self.train(descriptions, labels)
