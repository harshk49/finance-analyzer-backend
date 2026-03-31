"""Behavioral Insights Engine — deep spending pattern analysis.

Provides structured data for two core dimensions:

  1. **Day-of-week analysis**
     • Per-day spending totals, averages, and transaction counts
     • Weekend vs weekday comparison with overspend detection
     • Peak-spending day identification

  2. **Time-of-day analysis**
     • Hourly spending heatmap (0-23)
     • Time-band breakdown: Morning / Afternoon / Evening / Late-night
     • Late-night spending detection with severity scoring

Also generates actionable insight cards with recommendations.
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from server.schemas.analytics import BehavioralInsight
from server.utils.constants import CATEGORY_ICONS

logger = logging.getLogger(__name__)

# ── Day-of-week labels ──────────────────────────────────────────────
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ── Time-band definitions ──────────────────────────────────────────
_TIME_BANDS = {
    "early_morning": {"label": "Early Morning", "icon": "🌅", "hours": (5, 8)},
    "morning":       {"label": "Morning",       "icon": "☀️", "hours": (9, 11)},
    "afternoon":     {"label": "Afternoon",     "icon": "🌤️", "hours": (12, 16)},
    "evening":       {"label": "Evening",       "icon": "🌆", "hours": (17, 20)},
    "night":         {"label": "Night",         "icon": "🌙", "hours": (21, 23)},
    "late_night":    {"label": "Late Night",    "icon": "🦉", "hours": (0, 4)},
}


class BehaviorInsightsEngine:
    """Analyze spending behavior by day-of-week and time-of-day."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def analyze(self, transactions: list[dict]) -> dict:
        """Full behavioral analysis.

        Returns
        -------
        dict with keys:
            day_of_week     – per-day breakdown + weekend vs weekday
            time_of_day     – hourly heatmap + time-band breakdown
            insights        – list of BehavioralInsight cards
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["day_of_week"] = df["date"].dt.dayofweek   # 0=Mon, 6=Sun
        df["day_name"] = df["day_of_week"].map(lambda d: _DAY_NAMES[d])
        df["is_weekend"] = df["day_of_week"].isin([5, 6])

        debits = df[df["transaction_type"] == "debit"].copy()
        if debits.empty:
            return self._empty_result()

        dow_data = self._day_of_week_analysis(debits)
        tod_data = self._time_of_day_analysis(debits)
        insights = self._generate_insights(debits, dow_data, tod_data)

        return {
            "day_of_week": dow_data,
            "time_of_day": tod_data,
            "insights": [i.model_dump() for i in insights],
        }

    # ────────────────────────────────────────────────────────────────
    # Day-of-week analysis
    # ────────────────────────────────────────────────────────────────

    def _day_of_week_analysis(self, debits: pd.DataFrame) -> dict:
        """Compute per-day spending and weekend-vs-weekday comparison."""

        # ── Per-day breakdown ───────────────────────────────────────
        per_day = []
        for dow in range(7):
            day_df = debits[debits["day_of_week"] == dow]
            total = float(day_df["amount"].sum()) if not day_df.empty else 0.0
            count = int(len(day_df))
            avg = float(day_df["amount"].mean()) if not day_df.empty else 0.0

            per_day.append({
                "day_index": dow,
                "day_name": _DAY_NAMES[dow],
                "day_short": _DAY_SHORT[dow],
                "total_spend": round(total, 2),
                "transaction_count": count,
                "avg_amount": round(avg, 2),
                "is_weekend": dow in (5, 6),
            })

        # ── Peak day ───────────────────────────────────────────────
        peak = max(per_day, key=lambda d: d["total_spend"])

        # ── Weekend vs weekday ─────────────────────────────────────
        weekend_df = debits[debits["is_weekend"]]
        weekday_df = debits[~debits["is_weekend"]]

        weekend_total = float(weekend_df["amount"].sum()) if not weekend_df.empty else 0.0
        weekday_total = float(weekday_df["amount"].sum()) if not weekday_df.empty else 0.0

        weekend_avg_per_txn = float(weekend_df["amount"].mean()) if not weekend_df.empty else 0.0
        weekday_avg_per_txn = float(weekday_df["amount"].mean()) if not weekday_df.empty else 0.0

        # Normalize to per-day averages (weekend=2 days, weekday=5 days)
        n_weeks = max(1, (debits["date"].max() - debits["date"].min()).days / 7)
        weekend_avg_per_day = weekend_total / max(n_weeks * 2, 1)
        weekday_avg_per_day = weekday_total / max(n_weeks * 5, 1)

        overspend_pct = (
            round((weekend_avg_per_day - weekday_avg_per_day) / weekday_avg_per_day * 100, 1)
            if weekday_avg_per_day > 0 else 0.0
        )

        return {
            "per_day": per_day,
            "peak_day": peak["day_name"],
            "peak_day_total": peak["total_spend"],
            "weekend_vs_weekday": {
                "weekend_total": round(weekend_total, 2),
                "weekday_total": round(weekday_total, 2),
                "weekend_transaction_count": int(len(weekend_df)),
                "weekday_transaction_count": int(len(weekday_df)),
                "weekend_avg_per_transaction": round(weekend_avg_per_txn, 2),
                "weekday_avg_per_transaction": round(weekday_avg_per_txn, 2),
                "weekend_avg_per_day": round(weekend_avg_per_day, 2),
                "weekday_avg_per_day": round(weekday_avg_per_day, 2),
                "overspend_pct": overspend_pct,
                "is_overspending": overspend_pct > 20,
            },
        }

    # ────────────────────────────────────────────────────────────────
    # Time-of-day analysis
    # ────────────────────────────────────────────────────────────────

    def _time_of_day_analysis(self, debits: pd.DataFrame) -> dict:
        """Compute hourly heatmap and time-band spending breakdown."""

        has_time = (
            "time_hour" in debits.columns
            and debits["time_hour"].notna().any()
        )

        if not has_time:
            return {
                "hourly_heatmap": [],
                "time_bands": [],
                "late_night": self._empty_late_night(),
                "has_time_data": False,
            }

        timed = debits[debits["time_hour"].notna()].copy()
        timed["hour"] = timed["time_hour"].astype(int)

        # ── Hourly heatmap ─────────────────────────────────────────
        hourly = []
        for h in range(24):
            h_df = timed[timed["hour"] == h]
            hourly.append({
                "hour": h,
                "label": f"{h:02d}:00",
                "total_spend": round(float(h_df["amount"].sum()), 2),
                "transaction_count": int(len(h_df)),
                "avg_amount": round(float(h_df["amount"].mean()), 2) if not h_df.empty else 0.0,
            })

        # ── Time-band breakdown ────────────────────────────────────
        bands = []
        for band_key, band_def in _TIME_BANDS.items():
            h_start, h_end = band_def["hours"]
            if h_start <= h_end:
                band_df = timed[timed["hour"].between(h_start, h_end)]
            else:
                # Wraps midnight (late_night: 0-4)
                band_df = timed[timed["hour"].between(h_start, 23) | timed["hour"].between(0, h_end)]

            total = float(band_df["amount"].sum()) if not band_df.empty else 0.0
            count = int(len(band_df))
            all_total = float(timed["amount"].sum())
            pct = round(total / all_total * 100, 1) if all_total > 0 else 0.0

            # Top category in this band
            top_cat = "N/A"
            if not band_df.empty and "category" in band_df.columns:
                cat_totals = band_df.groupby("category")["amount"].sum()
                if not cat_totals.empty:
                    top_cat = str(cat_totals.idxmax())

            bands.append({
                "key": band_key,
                "label": band_def["label"],
                "icon": band_def["icon"],
                "hours": f"{h_start:02d}:00–{h_end:02d}:59",
                "total_spend": round(total, 2),
                "transaction_count": count,
                "percent_of_total": pct,
                "top_category": top_cat,
            })

        # ── Late-night detection ───────────────────────────────────
        late_night = self._detect_late_night(timed)

        return {
            "hourly_heatmap": hourly,
            "time_bands": bands,
            "late_night": late_night,
            "has_time_data": True,
        }

    def _detect_late_night(self, timed: pd.DataFrame) -> dict:
        """Detect and score late-night spending (10pm–4am)."""
        late = timed[
            timed["hour"].between(22, 23) | timed["hour"].between(0, 4)
        ]

        if late.empty:
            return self._empty_late_night()

        total = float(late["amount"].sum())
        count = int(len(late))
        all_total = float(timed["amount"].sum())
        pct = round(total / all_total * 100, 1) if all_total > 0 else 0.0

        # Top merchants in late-night
        top_merchants = []
        if "merchant_clean" in late.columns:
            merch_totals = late.groupby("merchant_clean")["amount"].agg(["sum", "count"])
            merch_totals = merch_totals.sort_values("sum", ascending=False).head(5)
            for merchant, row in merch_totals.iterrows():
                top_merchants.append({
                    "merchant": str(merchant),
                    "total": round(float(row["sum"]), 2),
                    "count": int(row["count"]),
                })

        # Severity
        if pct > 20 or count > 15:
            severity = "high"
        elif pct > 10 or count > 8:
            severity = "medium"
        else:
            severity = "low"

        return {
            "detected": count >= 3,
            "total_spend": round(total, 2),
            "transaction_count": count,
            "percent_of_total": pct,
            "avg_amount": round(total / count, 2) if count > 0 else 0.0,
            "severity": severity,
            "top_merchants": top_merchants,
        }

    # ────────────────────────────────────────────────────────────────
    # Insight cards
    # ────────────────────────────────────────────────────────────────

    def _generate_insights(
        self, debits: pd.DataFrame, dow: dict, tod: dict,
    ) -> list[BehavioralInsight]:
        """Generate actionable insight cards from analysis data."""
        insights: list[BehavioralInsight] = []

        # ── Weekend overspending ───────────────────────────────────
        wvw = dow.get("weekend_vs_weekday", {})
        if wvw.get("is_overspending"):
            pct = wvw["overspend_pct"]
            insights.append(BehavioralInsight(
                title="Weekend Overspending",
                description=(
                    f"You spend {pct}% more per day on weekends "
                    f"(₹{wvw['weekend_avg_per_day']:,.0f}/day) "
                    f"vs weekdays (₹{wvw['weekday_avg_per_day']:,.0f}/day)."
                ),
                severity="warning" if pct > 50 else "info",
                icon="📅",
                value=f"+{pct}%",
                recommendation="Set a weekend budget cap or plan free activities to cut discretionary spend.",
            ))

        # ── Peak spending day ──────────────────────────────────────
        peak = dow.get("peak_day", "")
        peak_total = dow.get("peak_day_total", 0)
        if peak and peak_total > 0:
            avg_daily = sum(d["total_spend"] for d in dow["per_day"]) / 7
            if peak_total > avg_daily * 1.5:
                insights.append(BehavioralInsight(
                    title=f"{peak} Is Your Biggest Spending Day",
                    description=(
                        f"You spend ₹{peak_total:,.0f} total on {peak}s — "
                        f"{round(peak_total / avg_daily * 100 - 100)}% above your daily average."
                    ),
                    severity="info",
                    icon="📊",
                    value=f"₹{peak_total:,.0f}",
                    recommendation=f"Review what drives your {peak} spending and see if it's avoidable.",
                ))

        # ── Late-night spending ────────────────────────────────────
        late = tod.get("late_night", {})
        if late.get("detected"):
            insights.append(BehavioralInsight(
                title="Late Night Spending Detected",
                description=(
                    f"{late['transaction_count']} transactions between 10pm–4am, "
                    f"totaling ₹{late['total_spend']:,.0f} "
                    f"({late['percent_of_total']}% of timed spending)."
                ),
                severity="warning" if late["severity"] in ("medium", "high") else "info",
                icon="🦉",
                value=f"₹{late['total_spend']:,.0f}",
                recommendation="Late-night purchases are often impulsive. Try a 24-hour cooling-off rule.",
            ))

        # ── Morning vs evening pattern ─────────────────────────────
        bands = {b["key"]: b for b in tod.get("time_bands", [])}
        morning = bands.get("morning", {})
        evening = bands.get("evening", {})
        if morning.get("total_spend", 0) > 0 and evening.get("total_spend", 0) > 0:
            ratio = evening["total_spend"] / morning["total_spend"]
            if ratio > 3:
                insights.append(BehavioralInsight(
                    title="Evening-Heavy Spender",
                    description=(
                        f"You spend {ratio:.1f}x more in the evening (₹{evening['total_spend']:,.0f}) "
                        f"than in the morning (₹{morning['total_spend']:,.0f})."
                    ),
                    severity="info",
                    icon="🌆",
                    value=f"{ratio:.1f}x",
                    recommendation="Evening spending often includes dining out and entertainment. Plan ahead.",
                ))

        # ── Spending concentration by category ─────────────────────
        if "category" in debits.columns:
            cat_totals = debits.groupby("category")["amount"].sum()
            total = cat_totals.sum()
            if total > 0:
                top_cat = str(cat_totals.idxmax())
                top_pct = cat_totals.max() / total * 100
                if top_pct > 40:
                    icon = CATEGORY_ICONS.get(top_cat, "⚠️")
                    insights.append(BehavioralInsight(
                        title="Spending Concentration Risk",
                        description=f"{top_pct:.0f}% of spending is in '{top_cat}'.",
                        severity="warning",
                        icon=icon,
                        value=f"{top_pct:.0f}%",
                        recommendation=f"Diversify or find ways to reduce {top_cat} costs.",
                    ))

        # ── Dining-out frequency ───────────────────────────────────
        if "category" in debits.columns and "month" in debits.columns:
            food = debits[debits["category"] == "Food & Dining"]
            if len(food) >= 10:
                avg_per_month = food.groupby("month").size().mean()
                if avg_per_month > 15:
                    insights.append(BehavioralInsight(
                        title="Frequent Dining Out",
                        description=f"~{avg_per_month:.0f} food orders per month.",
                        severity="info",
                        icon="🍔",
                        value=f"{avg_per_month:.0f}/mo",
                        recommendation="Cooking 5 more meals/month could save ₹2,000+.",
                    ))

        return insights

    # ────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_late_night() -> dict:
        return {
            "detected": False,
            "total_spend": 0,
            "transaction_count": 0,
            "percent_of_total": 0,
            "avg_amount": 0,
            "severity": "low",
            "top_merchants": [],
        }

    @staticmethod
    def _empty_result() -> dict:
        return {
            "day_of_week": {"per_day": [], "peak_day": None, "peak_day_total": 0, "weekend_vs_weekday": {}},
            "time_of_day": {"hourly_heatmap": [], "time_bands": [], "late_night": {}, "has_time_data": False},
            "insights": [],
        }
