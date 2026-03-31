"""Monthly Summary Engine — per-month financial snapshots with comparisons.

For each month, calculates:
  • Total spend / total income / net savings / savings rate
  • Category breakdown
  • Top merchants
  • Day-count and per-day averages

Cross-month analysis:
  • Month-over-month change (absolute + percentage)
  • Best / worst months
  • Trend direction (improving / stable / declining)
  • Rolling average comparison
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from server.utils.constants import CATEGORY_ICONS

logger = logging.getLogger(__name__)


class MonthlySummaryEngine:
    """Generate monthly summaries with cross-month comparisons."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def summarize(
        self,
        transactions: list[dict],
        target_month: Optional[str] = None,
    ) -> dict:
        """Generate monthly summaries.

        Parameters
        ----------
        transactions : list[dict]
            Structured transactions.
        target_month : str, optional
            If provided (format ``YYYY-MM``), returns detailed summary for
            that month only. Otherwise returns all months.

        Returns
        -------
        dict with keys:
            months          – list of per-month summaries
            comparison      – month-over-month comparison data
            overview        – aggregate stats across all months
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)

        # Build per-month summaries
        all_months = sorted(df["month"].unique())
        monthly_data = [self._single_month(df, m) for m in all_months]

        # Add month-over-month comparisons
        monthly_data = self._add_comparisons(monthly_data)

        # If a target month was requested, filter
        if target_month:
            target_data = [m for m in monthly_data if m["month"] == target_month]
            if not target_data:
                return self._empty_result()
            monthly_data = target_data

        # Aggregate overview
        overview = self._compute_overview(monthly_data)

        return {
            "months": monthly_data,
            "comparison": self._build_comparison_table(monthly_data),
            "overview": overview,
        }

    # ────────────────────────────────────────────────────────────────
    # Single-month summary
    # ────────────────────────────────────────────────────────────────

    def _single_month(self, df: pd.DataFrame, month: str) -> dict:
        """Compute summary for a single month."""
        mdf = df[df["month"] == month]
        debits = mdf[mdf["transaction_type"] == "debit"]
        credits = mdf[mdf["transaction_type"] == "credit"]

        total_spend = float(debits["amount"].sum())
        total_income = float(credits["amount"].sum())
        net_savings = total_income - total_spend
        savings_rate = round(net_savings / total_income * 100, 1) if total_income > 0 else 0.0

        # Date range and per-day avg
        date_min = mdf["date"].min()
        date_max = mdf["date"].max()
        n_days = max((date_max - date_min).days + 1, 1)
        avg_daily_spend = round(total_spend / n_days, 2)

        # Category breakdown (debits only)
        categories = []
        if not debits.empty and "category" in debits.columns:
            cat_agg = debits.groupby("category")["amount"].agg(["sum", "count"])
            cat_agg = cat_agg.sort_values("sum", ascending=False)
            for cat, row in cat_agg.iterrows():
                categories.append({
                    "category": str(cat),
                    "total": round(float(row["sum"]), 2),
                    "count": int(row["count"]),
                    "percentage": round(float(row["sum"]) / total_spend * 100, 1) if total_spend > 0 else 0,
                    "icon": CATEGORY_ICONS.get(str(cat), "💰"),
                })

        # Top merchants (debits)
        top_merchants = []
        if not debits.empty and "merchant_clean" in debits.columns:
            merch_agg = debits.groupby("merchant_clean")["amount"].agg(["sum", "count"])
            merch_agg = merch_agg.sort_values("sum", ascending=False).head(5)
            for merchant, row in merch_agg.iterrows():
                top_merchants.append({
                    "merchant": str(merchant),
                    "total": round(float(row["sum"]), 2),
                    "count": int(row["count"]),
                })

        return {
            "month": month,
            "total_spend": round(total_spend, 2),
            "total_income": round(total_income, 2),
            "net_savings": round(net_savings, 2),
            "savings_rate": savings_rate,
            "transaction_count": int(len(mdf)),
            "debit_count": int(len(debits)),
            "credit_count": int(len(credits)),
            "avg_daily_spend": avg_daily_spend,
            "date_range": {
                "start": str(date_min.date()),
                "end": str(date_max.date()),
            },
            "categories": categories,
            "top_merchants": top_merchants,
            # Populated by _add_comparisons()
            "vs_previous": None,
        }

    # ────────────────────────────────────────────────────────────────
    # Month-over-month comparison
    # ────────────────────────────────────────────────────────────────

    def _add_comparisons(self, months: list[dict]) -> list[dict]:
        """Add ``vs_previous`` comparison to each month (starting from 2nd)."""
        for i in range(len(months)):
            if i == 0:
                months[i]["vs_previous"] = None
                continue

            curr = months[i]
            prev = months[i - 1]

            spend_change = curr["total_spend"] - prev["total_spend"]
            spend_change_pct = (
                round(spend_change / prev["total_spend"] * 100, 1)
                if prev["total_spend"] > 0 else 0.0
            )

            income_change = curr["total_income"] - prev["total_income"]
            income_change_pct = (
                round(income_change / prev["total_income"] * 100, 1)
                if prev["total_income"] > 0 else 0.0
            )

            savings_change = curr["net_savings"] - prev["net_savings"]

            # Status: improved if savings increased or spending decreased
            if curr["net_savings"] > prev["net_savings"]:
                status = "improved"
            elif curr["net_savings"] < prev["net_savings"]:
                status = "declined"
            else:
                status = "unchanged"

            # Category changes
            curr_cats = {c["category"]: c["total"] for c in curr.get("categories", [])}
            prev_cats = {c["category"]: c["total"] for c in prev.get("categories", [])}
            all_cats = set(curr_cats.keys()) | set(prev_cats.keys())

            biggest_increase = {"category": None, "change": 0.0, "change_pct": 0.0}
            biggest_decrease = {"category": None, "change": 0.0, "change_pct": 0.0}

            for cat in all_cats:
                curr_val = curr_cats.get(cat, 0)
                prev_val = prev_cats.get(cat, 0)
                change = curr_val - prev_val
                change_pct = round(change / prev_val * 100, 1) if prev_val > 0 else 0.0

                if change > biggest_increase["change"]:
                    biggest_increase = {"category": cat, "change": round(change, 2), "change_pct": change_pct}
                if change < biggest_decrease["change"]:
                    biggest_decrease = {"category": cat, "change": round(change, 2), "change_pct": change_pct}

            months[i]["vs_previous"] = {
                "previous_month": prev["month"],
                "status": status,
                "spend_change": round(spend_change, 2),
                "spend_change_pct": spend_change_pct,
                "income_change": round(income_change, 2),
                "income_change_pct": income_change_pct,
                "savings_change": round(savings_change, 2),
                "txn_count_change": curr["transaction_count"] - prev["transaction_count"],
                "biggest_category_increase": biggest_increase if biggest_increase["category"] else None,
                "biggest_category_decrease": biggest_decrease if biggest_decrease["category"] else None,
            }

        return months

    def _build_comparison_table(self, months: list[dict]) -> list[dict]:
        """Build a simple comparison table for all months."""
        return [
            {
                "month": m["month"],
                "spend": m["total_spend"],
                "income": m["total_income"],
                "savings": m["net_savings"],
                "savings_rate": m["savings_rate"],
                "txn_count": m["transaction_count"],
                "spend_change_pct": m["vs_previous"]["spend_change_pct"] if m["vs_previous"] else None,
                "status": m["vs_previous"]["status"] if m["vs_previous"] else None,
            }
            for m in months
        ]

    # ────────────────────────────────────────────────────────────────
    # Overview (cross-month aggregate)
    # ────────────────────────────────────────────────────────────────

    def _compute_overview(self, months: list[dict]) -> dict:
        """Aggregate stats across all months."""
        if not months:
            return {}

        spends = [m["total_spend"] for m in months]
        incomes = [m["total_income"] for m in months]
        savings = [m["net_savings"] for m in months]

        # Best / worst months
        best_month = max(months, key=lambda m: m["net_savings"])
        worst_month = min(months, key=lambda m: m["net_savings"])

        # Trend (linear regression slope on spending)
        trend_direction = "stable"
        trend_slope = 0.0
        if len(spends) >= 3:
            x = np.arange(len(spends), dtype=float)
            slope = float(np.polyfit(x, spends, 1)[0])
            avg_spend = float(np.mean(spends))
            normalized = slope / avg_spend if avg_spend > 0 else 0
            trend_slope = round(normalized * 100, 1)  # percentage change per month

            if normalized > 0.05:
                trend_direction = "increasing"
            elif normalized < -0.05:
                trend_direction = "decreasing"

        return {
            "total_months": len(months),
            "avg_monthly_spend": round(float(np.mean(spends)), 2),
            "avg_monthly_income": round(float(np.mean(incomes)), 2),
            "avg_monthly_savings": round(float(np.mean(savings)), 2),
            "total_spend": round(sum(spends), 2),
            "total_income": round(sum(incomes), 2),
            "total_savings": round(sum(savings), 2),
            "best_month": {
                "month": best_month["month"],
                "savings": best_month["net_savings"],
                "savings_rate": best_month["savings_rate"],
            },
            "worst_month": {
                "month": worst_month["month"],
                "savings": worst_month["net_savings"],
                "savings_rate": worst_month["savings_rate"],
            },
            "spending_trend": {
                "direction": trend_direction,
                "slope_pct_per_month": trend_slope,
                "description": {
                    "increasing": "Your spending is trending upward month over month.",
                    "decreasing": "Your spending is trending downward — great job!",
                    "stable": "Your spending has been relatively consistent.",
                }.get(trend_direction, ""),
            },
        }

    @staticmethod
    def _empty_result() -> dict:
        return {"months": [], "comparison": [], "overview": {}}
