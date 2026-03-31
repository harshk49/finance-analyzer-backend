"""Financial Momentum Engine — tracks whether financial health is improving.

Combines:
  • Month-over-month spending/savings change
  • 3-month rolling average trend
  • Savings rate trajectory
  • Category-level momentum (which categories are improving/worsening)
  • Composite momentum score (-100 to +100)

Positive score = finances improving.  Negative = declining.
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FinancialMomentumEngine:
    """Compute financial momentum with rolling averages and scoring."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def analyze(self, transactions: list[dict]) -> dict:
        """Full momentum analysis.

        Returns
        -------
        dict with keys:
            score             – composite score (-100 to +100)
            direction         – "improving" / "stable" / "declining"
            monthly_momentum  – per-month momentum data with rolling avgs
            savings_momentum  – savings rate trajectory
            category_momentum – per-category direction
            factors           – list of human-readable momentum factors
            recommendation    – actionable advice
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)

        months = sorted(df["month"].unique())
        if len(months) < 2:
            return self._insufficient_data()

        debits = df[df["transaction_type"] == "debit"].copy()
        credits = df[df["transaction_type"] == "credit"].copy()

        monthly_momentum = self._monthly_momentum(df, months)
        savings_momentum = self._savings_momentum(df, months)
        category_momentum = self._category_momentum(debits, months)
        score, direction, factors = self._compute_score(
            monthly_momentum, savings_momentum, category_momentum,
        )

        return {
            "score": score,
            "direction": direction,
            "monthly_momentum": monthly_momentum,
            "savings_momentum": savings_momentum,
            "category_momentum": category_momentum,
            "factors": factors,
            "recommendation": self._get_recommendation(direction, factors),
        }

    # ────────────────────────────────────────────────────────────────
    # Monthly momentum (spending + rolling averages)
    # ────────────────────────────────────────────────────────────────

    def _monthly_momentum(self, df: pd.DataFrame, months: list) -> list[dict]:
        """Per-month spending with MoM change and rolling averages."""
        spend_values = []
        for month in months:
            mdf = df[(df["month"] == month) & (df["transaction_type"] == "debit")]
            spend_values.append(float(mdf["amount"].sum()))

        series = pd.Series(spend_values)
        roll_3 = series.rolling(window=3, min_periods=1).mean()

        rows = []
        for i, month in enumerate(months):
            mom_change = None
            mom_change_pct = None
            if i > 0 and spend_values[i - 1] > 0:
                mom_change = round(spend_values[i] - spend_values[i - 1], 2)
                mom_change_pct = round(
                    (spend_values[i] - spend_values[i - 1]) / spend_values[i - 1] * 100, 1
                )

            deviation = spend_values[i] - float(roll_3.iloc[i])
            rows.append({
                "month": str(month),
                "spend": round(spend_values[i], 2),
                "rolling_3m_avg": round(float(roll_3.iloc[i]), 2),
                "mom_change": mom_change,
                "mom_change_pct": mom_change_pct,
                "deviation_from_avg": round(deviation, 2),
                "is_above_average": deviation > 0,
            })

        return rows

    # ────────────────────────────────────────────────────────────────
    # Savings momentum
    # ────────────────────────────────────────────────────────────────

    def _savings_momentum(self, df: pd.DataFrame, months: list) -> dict:
        """Track savings rate trend over time."""
        rates = []
        for month in months:
            mdf = df[df["month"] == month]
            income = float(mdf[mdf["transaction_type"] == "credit"]["amount"].sum())
            expense = float(mdf[mdf["transaction_type"] == "debit"]["amount"].sum())
            rate = round((income - expense) / income * 100, 1) if income > 0 else 0
            rates.append({
                "month": str(month),
                "savings_rate": rate,
                "income": round(income, 2),
                "expense": round(expense, 2),
                "savings": round(income - expense, 2),
            })

        # Trend
        rate_values = [r["savings_rate"] for r in rates]
        if len(rate_values) >= 3:
            x = np.arange(len(rate_values), dtype=float)
            slope = float(np.polyfit(x, rate_values, 1)[0])
            trend = "improving" if slope > 0.5 else ("declining" if slope < -0.5 else "stable")
        elif len(rate_values) == 2:
            diff = rate_values[-1] - rate_values[0]
            trend = "improving" if diff > 2 else ("declining" if diff < -2 else "stable")
        else:
            trend = "stable"

        return {
            "monthly": rates,
            "current_rate": rate_values[-1] if rate_values else 0,
            "avg_rate": round(float(np.mean(rate_values)), 1) if rate_values else 0,
            "trend": trend,
        }

    # ────────────────────────────────────────────────────────────────
    # Category momentum
    # ────────────────────────────────────────────────────────────────

    def _category_momentum(self, debits: pd.DataFrame, months: list) -> list[dict]:
        """Per-category direction (which are increasing vs decreasing)."""
        if debits.empty or "category" not in debits.columns or len(months) < 2:
            return []

        categories = debits["category"].unique()
        result = []

        for cat in categories:
            cat_monthly = []
            for month in months:
                mdf = debits[(debits["month"] == month) & (debits["category"] == cat)]
                cat_monthly.append(float(mdf["amount"].sum()))

            if len(cat_monthly) < 2:
                continue

            # Linear trend
            x = np.arange(len(cat_monthly), dtype=float)
            slope = float(np.polyfit(x, cat_monthly, 1)[0])
            avg = float(np.mean(cat_monthly))
            normalized = slope / avg if avg > 0 else 0

            if normalized > 0.05:
                direction = "increasing"
            elif normalized < -0.05:
                direction = "decreasing"
            else:
                direction = "stable"

            # Recent vs previous
            recent = cat_monthly[-1]
            prev = cat_monthly[-2]
            mom_change = round(recent - prev, 2)
            mom_pct = round((recent - prev) / prev * 100, 1) if prev > 0 else 0

            result.append({
                "category": str(cat),
                "direction": direction,
                "current_monthly": round(recent, 2),
                "previous_monthly": round(prev, 2),
                "mom_change": mom_change,
                "mom_change_pct": mom_pct,
                "avg_monthly": round(avg, 2),
                "trend_slope": round(normalized * 100, 1),
            })

        # Sort: biggest increases first (worsening categories at top)
        return sorted(result, key=lambda c: c["mom_change"], reverse=True)

    # ────────────────────────────────────────────────────────────────
    # Composite score
    # ────────────────────────────────────────────────────────────────

    def _compute_score(
        self,
        monthly: list[dict],
        savings: dict,
        categories: list[dict],
    ) -> tuple[int, str, list[str]]:
        """Compute composite momentum score (-100 to +100).

        Components (weighted):
          • Spending trend (40%)    — is spending decreasing?
          • Savings trend (35%)     — is savings rate growing?
          • Category health (25%)   — are more categories decreasing than increasing?
        """
        factors: list[str] = []
        score = 0.0

        # ── Spending trend (40%) ───────────────────────────────────
        if len(monthly) >= 2:
            spend_values = [m["spend"] for m in monthly]
            x = np.arange(len(spend_values), dtype=float)
            slope = float(np.polyfit(x, spend_values, 1)[0])
            avg = float(np.mean(spend_values))
            normalized = slope / avg if avg > 0 else 0

            # Negative slope = improving (spending going down)
            spending_score = max(-40, min(40, -normalized * 400))
            score += spending_score

            if spending_score > 10:
                factors.append("Spending is trending downward ✅")
            elif spending_score < -10:
                factors.append("Spending is trending upward ⚠️")
            else:
                factors.append("Spending is relatively stable")

            # Recent vs rolling average
            if monthly[-1]["is_above_average"]:
                score -= 5
                factors.append("Last month was above your rolling average")
            else:
                score += 5
                factors.append("Last month was below your rolling average ✅")

        # ── Savings trend (35%) ────────────────────────────────────
        savings_trend = savings.get("trend", "stable")
        if savings_trend == "improving":
            score += 35
            factors.append("Savings rate is improving ✅")
        elif savings_trend == "declining":
            score -= 35
            factors.append("Savings rate is declining ⚠️")
        else:
            factors.append("Savings rate is stable")

        # ── Category health (25%) ─────────────────────────────────
        if categories:
            increasing = sum(1 for c in categories if c["direction"] == "increasing")
            decreasing = sum(1 for c in categories if c["direction"] == "decreasing")
            total_cats = len(categories)

            if total_cats > 0:
                health_ratio = (decreasing - increasing) / total_cats
                cat_score = health_ratio * 25
                score += cat_score

                if decreasing > increasing:
                    factors.append(f"{decreasing}/{total_cats} spending categories are decreasing ✅")
                elif increasing > decreasing:
                    factors.append(f"{increasing}/{total_cats} spending categories are increasing ⚠️")

        # ── Final score & direction ────────────────────────────────
        final_score = int(max(-100, min(100, score)))
        if final_score > 15:
            direction = "improving"
        elif final_score < -15:
            direction = "declining"
        else:
            direction = "stable"

        return final_score, direction, factors

    @staticmethod
    def _get_recommendation(direction: str, factors: list[str]) -> str:
        recs = {
            "improving": "Your financial trajectory is positive. Keep the momentum going by maintaining your current habits.",
            "stable": "Your finances are stable. Look for small optimizations to shift into growth mode.",
            "declining": "Your financial health needs attention. Review the factors above and focus on the biggest drivers.",
        }
        return recs.get(direction, "")

    # ────────────────────────────────────────────────────────────────
    # Empty results
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_result() -> dict:
        return {
            "score": 0, "direction": "stable",
            "monthly_momentum": [], "savings_momentum": {},
            "category_momentum": [], "factors": ["No data"],
            "recommendation": "",
        }

    @staticmethod
    def _insufficient_data() -> dict:
        return {
            "score": 0, "direction": "stable",
            "monthly_momentum": [], "savings_momentum": {},
            "category_momentum": [],
            "factors": ["Need at least 2 months of data for momentum analysis"],
            "recommendation": "Upload more months of data to unlock momentum tracking.",
        }
