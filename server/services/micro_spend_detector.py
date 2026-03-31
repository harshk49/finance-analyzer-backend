"""Micro-Spend Detector — finds small transactions that silently drain money.

Targets "latte factor" spending: frequent small purchases (< ₹300) that
individually feel insignificant but accumulate into serious leaks.

Output:
  • Per-merchant breakdown (count, total, avg)
  • Ranked merchants by total drain
  • Summary stats (total micro-spend, % of all spending, monthly projection)
  • Actionable recommendations
"""
import logging
from collections import defaultdict
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Configurable thresholds ─────────────────────────────────────────
MICRO_THRESHOLD = 300.0        # ₹300 — max amount to consider "micro"
MIN_FREQUENCY = 3              # Must occur ≥ 3 times to be a pattern
TOP_N_MERCHANTS = 15           # Return top N merchants by drain


class MicroSpendDetector:
    """Detect and rank micro-spending patterns."""

    def __init__(
        self,
        threshold: float = MICRO_THRESHOLD,
        min_frequency: int = MIN_FREQUENCY,
    ):
        self.threshold = threshold
        self.min_frequency = min_frequency

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def analyze(self, transactions: list[dict]) -> dict:
        """Run full micro-spend analysis.

        Parameters
        ----------
        transactions : list[dict]
            Structured transaction dicts (must have ``amount``,
            ``transaction_type``, ``merchant_clean``, ``category``, ``date``).

        Returns
        -------
        dict with keys:
            merchants        – ranked list of micro-spend merchant breakdowns
            summary          – aggregate stats
            recommendations  – actionable tips
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)

        # Work only with debits
        debits = df[df["transaction_type"] == "debit"].copy()
        if debits.empty:
            return self._empty_result()

        # Filter micro transactions
        micro = debits[debits["amount"] <= self.threshold].copy()
        if micro.empty:
            return self._empty_result()

        # ── Per-merchant breakdown ──────────────────────────────────
        merchants = self._rank_merchants(micro)

        # ── Summary stats ───────────────────────────────────────────
        summary = self._compute_summary(micro, debits)

        # ── Recommendations ─────────────────────────────────────────
        recommendations = self._generate_recommendations(merchants, summary)

        return {
            "merchants": merchants,
            "summary": summary,
            "recommendations": recommendations,
        }

    # ────────────────────────────────────────────────────────────────
    # Internals
    # ────────────────────────────────────────────────────────────────

    def _rank_merchants(self, micro: pd.DataFrame) -> list[dict]:
        """Group by merchant, compute stats, rank by total amount."""
        if "merchant_clean" not in micro.columns:
            return []

        grouped = micro.groupby("merchant_clean").agg(
            count=("amount", "count"),
            total=("amount", "sum"),
            avg=("amount", "mean"),
            min_amount=("amount", "min"),
            max_amount=("amount", "max"),
            category=("category", lambda x: x.mode().iloc[0] if not x.mode().empty else "Uncategorized"),
        )

        # Only keep merchants with enough frequency
        frequent = grouped[grouped["count"] >= self.min_frequency]
        if frequent.empty:
            # Fall back: include all if none meet threshold
            frequent = grouped.head(TOP_N_MERCHANTS)

        ranked = frequent.sort_values("total", ascending=False).head(TOP_N_MERCHANTS)

        return [
            {
                "merchant": str(merchant),
                "count": int(row["count"]),
                "total_amount": round(float(row["total"]), 2),
                "avg_amount": round(float(row["avg"]), 2),
                "min_amount": round(float(row["min_amount"]), 2),
                "max_amount": round(float(row["max_amount"]), 2),
                "category": str(row["category"]),
                "drain_rank": rank + 1,
            }
            for rank, (merchant, row) in enumerate(ranked.iterrows())
        ]

    def _compute_summary(self, micro: pd.DataFrame, all_debits: pd.DataFrame) -> dict:
        """Compute aggregate micro-spending statistics."""
        total_micro = float(micro["amount"].sum())
        total_all = float(all_debits["amount"].sum())
        pct_of_spending = round(total_micro / total_all * 100, 1) if total_all > 0 else 0

        # Monthly projection
        if "date" in micro.columns:
            dates = pd.to_datetime(micro["date"])
            date_range_days = max((dates.max() - dates.min()).days, 1)
            months_covered = max(date_range_days / 30.44, 1)  # avg days/month
            monthly_avg = total_micro / months_covered
        else:
            monthly_avg = total_micro
            months_covered = 1

        # Unique merchants
        unique_merchants = micro["merchant_clean"].nunique() if "merchant_clean" in micro.columns else 0

        return {
            "total_micro_spend": round(total_micro, 2),
            "total_transactions": int(len(micro)),
            "avg_transaction": round(float(micro["amount"].mean()), 2),
            "percent_of_total_spending": pct_of_spending,
            "monthly_average": round(monthly_avg, 2),
            "yearly_projection": round(monthly_avg * 12, 2),
            "unique_merchants": unique_merchants,
            "threshold": self.threshold,
        }

    @staticmethod
    def _generate_recommendations(merchants: list[dict], summary: dict) -> list[dict]:
        """Generate actionable recommendations based on micro-spend patterns."""
        recs: list[dict] = []

        pct = summary.get("percent_of_total_spending", 0)
        yearly = summary.get("yearly_projection", 0)

        # Overall alert
        if pct > 25:
            recs.append({
                "type": "critical",
                "title": "High micro-spending detected",
                "description": (
                    f"Small transactions under ₹{MICRO_THRESHOLD:.0f} account for "
                    f"{pct}% of your total spending — that's ₹{yearly:,.0f}/year."
                ),
                "action": "Set a daily micro-spend budget of ₹100 to cut this in half.",
            })
        elif pct > 15:
            recs.append({
                "type": "warning",
                "title": "Noticeable micro-spending leaks",
                "description": (
                    f"₹{yearly:,.0f}/year goes to small purchases. "
                    f"That's {pct}% of total spending."
                ),
                "action": "Try a no-micro-spend day once a week.",
            })

        # Per-merchant recs (top 3)
        food_merchants = [m for m in merchants if m["category"] in ("Food & Dining", "Groceries")]
        if food_merchants:
            top = food_merchants[0]
            recs.append({
                "type": "info",
                "title": f"Frequent spender at {top['merchant']}",
                "description": (
                    f"{top['count']} transactions totaling ₹{top['total_amount']:,.0f}. "
                    f"Average ₹{top['avg_amount']:.0f} each."
                ),
                "action": f"Batch your {top['merchant']} orders to reduce frequency by 50%.",
            })

        # Savings potential
        if yearly > 5000:
            ten_pct = round(yearly * 0.10, 0)
            recs.append({
                "type": "tip",
                "title": "Potential annual saving",
                "description": (
                    f"Reducing micro-spending by just 10% would save ₹{ten_pct:,.0f}/year."
                ),
                "action": "Use a 15-minute delay rule before making small purchases.",
            })

        return recs

    @staticmethod
    def _empty_result() -> dict:
        return {
            "merchants": [],
            "summary": {
                "total_micro_spend": 0,
                "total_transactions": 0,
                "avg_transaction": 0,
                "percent_of_total_spending": 0,
                "monthly_average": 0,
                "yearly_projection": 0,
                "unique_merchants": 0,
                "threshold": MICRO_THRESHOLD,
            },
            "recommendations": [],
        }
