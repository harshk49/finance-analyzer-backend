"""Analytics Engine — core financial computations.

Provides:
  • Category breakdown with icons and merchant detail
  • Monthly trends (spending, income, net) with MoM change
  • Daily cash flow for granular charting
  • Per-category monthly trends (how each category evolves)
  • Top merchants across time
  • Rolling averages (3-month, 6-month) for smoothed trends
"""
from typing import Optional

import numpy as np
import pandas as pd

from server.schemas.analytics import (
    AnalyticsSummary, CategoryBreakdown, CashFlowData,
    MonthlySpending, TrendData,
)
from server.utils.constants import CATEGORY_ICONS


class AnalyticsEngine:
    """Compute financial analytics from transaction data."""

    # ────────────────────────────────────────────────────────────────
    # Main entry point
    # ────────────────────────────────────────────────────────────────

    def compute(self, transactions: list[dict]) -> AnalyticsSummary:
        """Compute full analytics summary from transaction list."""
        if not transactions:
            return self._empty_summary()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)
        df["day_of_week"] = df["date"].dt.dayofweek

        debits = df[df["transaction_type"] == "debit"]
        credits = df[df["transaction_type"] == "credit"]

        total_expenses = float(debits["amount"].sum())
        total_income = float(credits["amount"].sum())
        net_savings = total_income - total_expenses
        savings_rate = (net_savings / total_income * 100) if total_income > 0 else 0

        date_range_days = (df["date"].max() - df["date"].min()).days + 1
        avg_daily = total_expenses / max(date_range_days, 1)

        category_breakdown = self._category_breakdown(debits)
        top_cat = category_breakdown[0].category if category_breakdown else "N/A"
        monthly_spending = self._monthly_spending(df)
        cash_flow = self._cash_flow(df)
        trends = self._spending_trends(monthly_spending)

        return AnalyticsSummary(
            total_income=round(total_income, 2),
            total_expenses=round(total_expenses, 2),
            net_savings=round(net_savings, 2),
            savings_rate=round(savings_rate, 1),
            avg_daily_spend=round(avg_daily, 2),
            top_category=top_cat,
            transaction_count=len(df),
            date_range={
                "start": df["date"].min().strftime("%Y-%m-%d"),
                "end": df["date"].max().strftime("%Y-%m-%d"),
            },
            monthly_spending=monthly_spending,
            category_breakdown=category_breakdown,
            cash_flow=cash_flow,
            trends=trends,
        )

    # ────────────────────────────────────────────────────────────────
    # Extended analytics (dict-based for flexibility)
    # ────────────────────────────────────────────────────────────────

    def compute_extended(self, transactions: list[dict]) -> dict:
        """Compute extended analytics including category trends,
        rolling averages, merchant breakdown, and daily cash flow.

        Returns a plain dict for maximum frontend flexibility.
        """
        if not transactions:
            return self._empty_extended()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)

        debits = df[df["transaction_type"] == "debit"].copy()
        credits = df[df["transaction_type"] == "credit"].copy()

        total_expenses = float(debits["amount"].sum())
        total_income = float(credits["amount"].sum())

        return {
            # Core KPIs
            "kpis": {
                "total_income": round(total_income, 2),
                "total_expenses": round(total_expenses, 2),
                "net_savings": round(total_income - total_expenses, 2),
                "savings_rate": round(
                    (total_income - total_expenses) / total_income * 100, 1
                ) if total_income > 0 else 0,
                "avg_daily_spend": round(
                    total_expenses / max((df["date"].max() - df["date"].min()).days + 1, 1), 2
                ),
                "transaction_count": len(df),
                "debit_count": len(debits),
                "credit_count": len(credits),
                "date_range": {
                    "start": df["date"].min().strftime("%Y-%m-%d"),
                    "end": df["date"].max().strftime("%Y-%m-%d"),
                },
            },
            # Category breakdown
            "category_breakdown": self._category_breakdown_extended(debits),
            # Monthly trends
            "monthly_trends": self._monthly_trends(df),
            # Per-category monthly trends
            "category_trends": self._category_monthly_trends(debits),
            # Daily cash flow
            "daily_cash_flow": self._daily_cash_flow(df),
            # Rolling averages
            "rolling_averages": self._rolling_averages(df),
            # Top merchants
            "top_merchants": self._top_merchants(debits),
        }

    # ────────────────────────────────────────────────────────────────
    # Category breakdown
    # ────────────────────────────────────────────────────────────────

    def _category_breakdown(self, debits: pd.DataFrame) -> list[CategoryBreakdown]:
        """Compute spending by category (Pydantic model)."""
        if debits.empty:
            return []

        total = float(debits["amount"].sum())
        grouped = debits.groupby("category").agg(
            total=("amount", "sum"),
            count=("amount", "count"),
        ).sort_values("total", ascending=False)

        return [
            CategoryBreakdown(
                category=str(cat),
                total=round(float(row["total"]), 2),
                percentage=round(float(row["total"]) / total * 100, 1),
                count=int(row["count"]),
                icon=CATEGORY_ICONS.get(str(cat), "💰"),
            )
            for cat, row in grouped.iterrows()
        ]

    def _category_breakdown_extended(self, debits: pd.DataFrame) -> list[dict]:
        """Category breakdown with top merchants per category."""
        if debits.empty or "category" not in debits.columns:
            return []

        total = float(debits["amount"].sum())
        grouped = debits.groupby("category").agg(
            total=("amount", "sum"),
            count=("amount", "count"),
            avg=("amount", "mean"),
        ).sort_values("total", ascending=False)

        result = []
        for cat, row in grouped.iterrows():
            cat_str = str(cat)
            cat_df = debits[debits["category"] == cat_str]

            # Top merchants in this category
            top_merchants = []
            if "merchant_clean" in cat_df.columns:
                merch = cat_df.groupby("merchant_clean")["amount"].agg(["sum", "count"])
                merch = merch.sort_values("sum", ascending=False).head(3)
                for m, mr in merch.iterrows():
                    top_merchants.append({
                        "merchant": str(m),
                        "total": round(float(mr["sum"]), 2),
                        "count": int(mr["count"]),
                    })

            result.append({
                "category": cat_str,
                "total": round(float(row["total"]), 2),
                "percentage": round(float(row["total"]) / total * 100, 1),
                "count": int(row["count"]),
                "avg_transaction": round(float(row["avg"]), 2),
                "icon": CATEGORY_ICONS.get(cat_str, "💰"),
                "top_merchants": top_merchants,
            })

        return result

    # ────────────────────────────────────────────────────────────────
    # Monthly trends
    # ────────────────────────────────────────────────────────────────

    def _monthly_spending(self, df: pd.DataFrame) -> list[MonthlySpending]:
        """Compute monthly spending and income (Pydantic model)."""
        results = []
        for month, group in df.groupby("month"):
            debits = float(group[group["transaction_type"] == "debit"]["amount"].sum())
            credits = float(group[group["transaction_type"] == "credit"]["amount"].sum())
            results.append(MonthlySpending(
                month=str(month),
                total_debit=round(debits, 2),
                total_credit=round(credits, 2),
                net=round(credits - debits, 2),
                transaction_count=len(group),
            ))
        return sorted(results, key=lambda x: x.month)

    def _monthly_trends(self, df: pd.DataFrame) -> list[dict]:
        """Monthly trends with MoM change % for spending, income, savings."""
        months = sorted(df["month"].unique())
        rows = []

        for i, month in enumerate(months):
            mdf = df[df["month"] == month]
            spend = float(mdf[mdf["transaction_type"] == "debit"]["amount"].sum())
            income = float(mdf[mdf["transaction_type"] == "credit"]["amount"].sum())
            savings = income - spend
            count = len(mdf)

            spend_change_pct = None
            income_change_pct = None
            savings_change_pct = None

            if i > 0:
                prev = rows[i - 1]
                if prev["spend"] > 0:
                    spend_change_pct = round((spend - prev["spend"]) / prev["spend"] * 100, 1)
                if prev["income"] > 0:
                    income_change_pct = round((income - prev["income"]) / prev["income"] * 100, 1)
                if prev["savings"] != 0:
                    savings_change_pct = round((savings - prev["savings"]) / abs(prev["savings"]) * 100, 1)

            rows.append({
                "month": str(month),
                "spend": round(spend, 2),
                "income": round(income, 2),
                "savings": round(savings, 2),
                "savings_rate": round(savings / income * 100, 1) if income > 0 else 0,
                "transaction_count": count,
                "spend_change_pct": spend_change_pct,
                "income_change_pct": income_change_pct,
                "savings_change_pct": savings_change_pct,
            })

        return rows

    def _category_monthly_trends(self, debits: pd.DataFrame) -> list[dict]:
        """Per-category spending across months for stacked charts."""
        if debits.empty or "category" not in debits.columns:
            return []

        months = sorted(debits["month"].unique())
        categories = debits.groupby("category")["amount"].sum().sort_values(ascending=False).index.tolist()

        result = []
        for month in months:
            mdf = debits[debits["month"] == month]
            cat_totals = mdf.groupby("category")["amount"].sum()

            entry = {"month": str(month)}
            for cat in categories:
                entry[cat] = round(float(cat_totals.get(cat, 0)), 2)
            entry["total"] = round(float(mdf["amount"].sum()), 2)
            result.append(entry)

        return result

    # ────────────────────────────────────────────────────────────────
    # Cash flow
    # ────────────────────────────────────────────────────────────────

    def _cash_flow(self, df: pd.DataFrame) -> list[CashFlowData]:
        """Monthly cash flow (Pydantic model)."""
        results = []
        for month, group in df.groupby("month"):
            income = float(group[group["transaction_type"] == "credit"]["amount"].sum())
            expenses = float(group[group["transaction_type"] == "debit"]["amount"].sum())
            results.append(CashFlowData(
                month=str(month),
                income=round(income, 2),
                expenses=round(expenses, 2),
                net=round(income - expenses, 2),
            ))
        return sorted(results, key=lambda x: x.month)

    def _daily_cash_flow(self, df: pd.DataFrame) -> list[dict]:
        """Daily cash flow for granular charting."""
        df_sorted = df.sort_values("date")
        daily_groups = df_sorted.groupby(df_sorted["date"].dt.date)

        rows = []
        cumulative_income = 0.0
        cumulative_expense = 0.0

        for day, group in daily_groups:
            income = float(group[group["transaction_type"] == "credit"]["amount"].sum())
            expense = float(group[group["transaction_type"] == "debit"]["amount"].sum())
            cumulative_income += income
            cumulative_expense += expense

            rows.append({
                "date": str(day),
                "income": round(income, 2),
                "expense": round(expense, 2),
                "net": round(income - expense, 2),
                "cumulative_income": round(cumulative_income, 2),
                "cumulative_expense": round(cumulative_expense, 2),
                "cumulative_net": round(cumulative_income - cumulative_expense, 2),
                "transaction_count": len(group),
            })

        return rows

    # ────────────────────────────────────────────────────────────────
    # Rolling averages
    # ────────────────────────────────────────────────────────────────

    def _rolling_averages(self, df: pd.DataFrame) -> dict:
        """Compute 3-month and 6-month rolling averages for spending."""
        months = sorted(df["month"].unique())
        monthly_spend = []

        for month in months:
            mdf = df[(df["month"] == month) & (df["transaction_type"] == "debit")]
            monthly_spend.append(float(mdf["amount"].sum()))

        spend_series = pd.Series(monthly_spend)

        # 3-month rolling average
        roll_3 = spend_series.rolling(window=3, min_periods=1).mean()
        # 6-month rolling average
        roll_6 = spend_series.rolling(window=6, min_periods=1).mean()

        entries = []
        for i, month in enumerate(months):
            entries.append({
                "month": str(month),
                "actual_spend": round(monthly_spend[i], 2),
                "rolling_3m_avg": round(float(roll_3.iloc[i]), 2),
                "rolling_6m_avg": round(float(roll_6.iloc[i]), 2),
                "deviation_from_3m": round(
                    monthly_spend[i] - float(roll_3.iloc[i]), 2
                ),
            })

        return {
            "monthly": entries,
            "current_3m_avg": round(float(roll_3.iloc[-1]), 2) if len(roll_3) > 0 else 0,
            "current_6m_avg": round(float(roll_6.iloc[-1]), 2) if len(roll_6) > 0 else 0,
        }

    # ────────────────────────────────────────────────────────────────
    # Top merchants
    # ────────────────────────────────────────────────────────────────

    def _top_merchants(self, debits: pd.DataFrame, n: int = 10) -> list[dict]:
        """Top merchants by total spend."""
        if debits.empty or "merchant_clean" not in debits.columns:
            return []

        total = float(debits["amount"].sum())
        grouped = debits.groupby("merchant_clean").agg(
            total=("amount", "sum"),
            count=("amount", "count"),
            avg=("amount", "mean"),
            category=("category", lambda x: x.mode().iloc[0] if not x.mode().empty else "Uncategorized"),
        ).sort_values("total", ascending=False).head(n)

        return [
            {
                "merchant": str(merchant),
                "total": round(float(row["total"]), 2),
                "percentage": round(float(row["total"]) / total * 100, 1) if total > 0 else 0,
                "count": int(row["count"]),
                "avg_transaction": round(float(row["avg"]), 2),
                "category": str(row["category"]),
                "icon": CATEGORY_ICONS.get(str(row["category"]), "💰"),
            }
            for merchant, row in grouped.iterrows()
        ]

    # ────────────────────────────────────────────────────────────────
    # Trends
    # ────────────────────────────────────────────────────────────────

    def _spending_trends(self, monthly: list[MonthlySpending]) -> list[TrendData]:
        """Compute spending trends with MoM change."""
        if len(monthly) < 2:
            return [TrendData(period=m.month, value=m.total_debit) for m in monthly]

        trends = []
        for i, m in enumerate(monthly):
            change_pct = None
            if i > 0:
                prev = monthly[i - 1].total_debit
                if prev > 0:
                    change_pct = round((m.total_debit - prev) / prev * 100, 1)
            trends.append(TrendData(
                period=m.month,
                value=m.total_debit,
                change_pct=change_pct,
            ))
        return trends

    # ────────────────────────────────────────────────────────────────
    # Empty results
    # ────────────────────────────────────────────────────────────────

    def _empty_summary(self) -> AnalyticsSummary:
        return AnalyticsSummary(
            total_income=0, total_expenses=0, net_savings=0,
            savings_rate=0, avg_daily_spend=0, top_category="N/A",
            transaction_count=0, date_range={"start": "", "end": ""},
            monthly_spending=[], category_breakdown=[],
            cash_flow=[], trends=[],
        )

    @staticmethod
    def _empty_extended() -> dict:
        return {
            "kpis": {}, "category_breakdown": [], "monthly_trends": [],
            "category_trends": [], "daily_cash_flow": [],
            "rolling_averages": {"monthly": [], "current_3m_avg": 0, "current_6m_avg": 0},
            "top_merchants": [],
        }
