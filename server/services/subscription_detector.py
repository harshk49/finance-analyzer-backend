"""Subscription Detector — identifies recurring payments with high accuracy.

Detection methodology:
  1. Group transactions by merchant_clean
  2. For each merchant with 2+ transactions:
     a. Check amount consistency (CV < 15%)
     b. Check interval regularity (weekly / monthly / quarterly / yearly)
     c. Score confidence from frequency count + variance
  3. Classify as "known" or "hidden" subscription
  4. Estimate total annual cost and next charge date

"Hidden" subscriptions are recurring charges the user might not be
consciously aware of — they don't match well-known streaming/SaaS names.
"""
import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Well-known subscription services ────────────────────────────────
# If a detected subscription matches one of these, it's "known".
_KNOWN_SERVICES = {
    "netflix", "spotify", "youtube", "hotstar", "amazon", "prime",
    "disney", "zee5", "sonyliv", "jiocinema", "apple", "icloud",
    "google one", "microsoft", "github", "dropbox", "notion",
    "chatgpt", "openai", "jio", "airtel", "bsnl", "vi", "vodafone",
    "tata play", "tata sky", "cult.fit", "cultfit", "gym",
}

# ── Periodicity definitions ─────────────────────────────────────────
# (label, min_days, max_days, max_std)
_PERIODS = [
    ("weekly",    5,   9,   2),
    ("biweekly",  12,  16,  3),
    ("monthly",   25,  35,  7),
    ("quarterly", 80, 100, 15),
    ("half-yearly", 170, 200, 20),
    ("yearly",   350, 380, 25),
]


class SubscriptionDetector:
    """Detect and analyze recurring (subscription) transactions."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def detect(self, transactions: list[dict]) -> dict:
        """Run full subscription detection.

        Parameters
        ----------
        transactions : list[dict]
            Structured transaction dicts.

        Returns
        -------
        dict with keys:
            subscriptions       – list of detected subscriptions
            summary             – aggregate stats
            hidden_subscriptions – subscriptions user may not be aware of
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        debits = df[df["transaction_type"] == "debit"].copy()
        if debits.empty or "merchant_clean" not in debits.columns:
            return self._empty_result()

        debits["date"] = pd.to_datetime(debits["date"])

        subscriptions = self._find_subscriptions(debits)

        # Split known vs hidden
        known = [s for s in subscriptions if not s["is_hidden"]]
        hidden = [s for s in subscriptions if s["is_hidden"]]

        summary = self._compute_summary(subscriptions)

        return {
            "subscriptions": subscriptions,
            "hidden_subscriptions": hidden,
            "summary": summary,
        }

    # ────────────────────────────────────────────────────────────────
    # Core detection
    # ────────────────────────────────────────────────────────────────

    def _find_subscriptions(self, debits: pd.DataFrame) -> list[dict]:
        """Iterate merchants and check for recurring patterns."""
        results: list[dict] = []

        for merchant, group in debits.groupby("merchant_clean"):
            if len(group) < 2:
                continue

            sub = self._analyze_merchant(str(merchant), group)
            if sub is not None:
                results.append(sub)

        return sorted(results, key=lambda s: s["annual_cost"], reverse=True)

    def _analyze_merchant(self, merchant: str, group: pd.DataFrame) -> Optional[dict]:
        """Analyze a single merchant's transactions for subscription patterns.

        Checks:
          1. Same merchant  (already grouped)
          2. Similar amount (CV < 15%)
          3. Periodic interval (matches a known period with acceptable std)
        """
        amounts = group["amount"].values
        dates = group["date"].sort_values()

        # ── Amount consistency ──────────────────────────────────────
        amount_mean = float(np.mean(amounts))
        amount_std = float(np.std(amounts))
        amount_cv = amount_std / amount_mean if amount_mean > 0 else float("inf")

        if amount_cv > 0.15:
            # Too much variance — not a subscription
            return None

        # ── Interval regularity ─────────────────────────────────────
        if len(dates) < 2:
            return None

        intervals = dates.diff().dropna().dt.days.values
        if len(intervals) == 0:
            return None

        avg_interval = float(np.mean(intervals))
        interval_std = float(np.std(intervals))

        frequency = None
        for label, min_d, max_d, max_s in _PERIODS:
            if min_d <= avg_interval <= max_d and interval_std <= max_s:
                frequency = label
                break

        if frequency is None:
            return None

        # ── Confidence scoring ──────────────────────────────────────
        confidence = self._compute_confidence(
            n_occurrences=len(group),
            amount_cv=amount_cv,
            interval_std=interval_std,
            avg_interval=avg_interval,
        )

        if confidence < 0.45:
            return None

        # ── Classification ──────────────────────────────────────────
        is_hidden = not any(k in merchant.lower() for k in _KNOWN_SERVICES)

        # ── Next expected charge ────────────────────────────────────
        last_date = dates.max()
        next_expected = last_date + pd.Timedelta(days=int(round(avg_interval)))

        # ── Annual cost projection ──────────────────────────────────
        charges_per_year = 365.25 / avg_interval
        annual_cost = round(amount_mean * charges_per_year, 2)

        # ── Category ───────────────────────────────────────────────
        category = (
            group["category"].mode().iloc[0]
            if "category" in group.columns and not group["category"].mode().empty
            else "Subscriptions"
        )

        return {
            "merchant": merchant,
            "amount": round(amount_mean, 2),
            "frequency": frequency,
            "confidence": round(confidence, 2),
            "category": category,
            "is_hidden": is_hidden,
            "occurrence_count": int(len(group)),
            "avg_interval_days": round(avg_interval, 1),
            "amount_variance": round(amount_cv * 100, 1),  # as percentage
            "annual_cost": annual_cost,
            "last_charged": str(last_date.date()) if hasattr(last_date, "date") else str(last_date)[:10],
            "next_expected": str(next_expected.date()) if hasattr(next_expected, "date") else str(next_expected)[:10],
        }

    @staticmethod
    def _compute_confidence(
        n_occurrences: int,
        amount_cv: float,
        interval_std: float,
        avg_interval: float,
    ) -> float:
        """Compute a 0-1 confidence score for a subscription match.

        Factors:
          • More occurrences → higher confidence (+0.08 per occurrence, capped)
          • Lower amount CV  → higher confidence
          • Lower interval std relative to interval → higher confidence
        """
        # Base (2 occurrences = 0.45)
        base = 0.30

        # Occurrence bonus: saturates at ~10 occurrences
        occ_bonus = min(0.40, n_occurrences * 0.08)

        # Amount consistency bonus: perfect = 0.15, cv=0.15 → 0
        amount_bonus = max(0.0, 0.15 * (1 - amount_cv / 0.15))

        # Interval regularity bonus
        relative_std = interval_std / avg_interval if avg_interval > 0 else 1
        interval_bonus = max(0.0, 0.15 * (1 - relative_std / 0.25))

        confidence = base + occ_bonus + amount_bonus + interval_bonus
        return min(0.99, confidence)

    # ────────────────────────────────────────────────────────────────
    # Summary
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_summary(subscriptions: list[dict]) -> dict:
        """Compute aggregate subscription statistics."""
        if not subscriptions:
            return {
                "total_subscriptions": 0,
                "known_subscriptions": 0,
                "hidden_subscriptions": 0,
                "total_monthly_cost": 0,
                "total_annual_cost": 0,
            }

        total_annual = sum(s["annual_cost"] for s in subscriptions)
        known_count = sum(1 for s in subscriptions if not s["is_hidden"])
        hidden_count = sum(1 for s in subscriptions if s["is_hidden"])

        return {
            "total_subscriptions": len(subscriptions),
            "known_subscriptions": known_count,
            "hidden_subscriptions": hidden_count,
            "total_monthly_cost": round(total_annual / 12, 2),
            "total_annual_cost": round(total_annual, 2),
        }

    @staticmethod
    def _empty_result() -> dict:
        return {
            "subscriptions": [],
            "hidden_subscriptions": [],
            "summary": {
                "total_subscriptions": 0,
                "known_subscriptions": 0,
                "hidden_subscriptions": 0,
                "total_monthly_cost": 0,
                "total_annual_cost": 0,
            },
        }
