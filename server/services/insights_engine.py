"""Behavioral Insights Engine — detects spending patterns and habits.

Identifies:
- Weekend overspending
- Late-night spending
- Micro-spending leaks
- Subscription detection
- Spending personality classification
- Financial momentum
- Regret spending detection
- Savings opportunities
"""
from collections import defaultdict, Counter
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from server.schemas.analytics import (
    BehavioralInsight, MicroSpendingAlert, SubscriptionItem,
    SpendingPersonality, FinancialMomentum, SavingsOpportunity,
    AnomalyItem
)
from server.utils.constants import SPENDING_PERSONALITIES, CATEGORY_ICONS


class InsightsEngine:
    """Generate behavioral insights from transaction data."""

    def generate_all(self, transactions: list[dict]) -> dict:
        """Generate all behavioral insights."""
        if not transactions:
            return {"insights": [], "micro_spending": [], "subscriptions": [],
                    "personality": None, "momentum": None, "savings_opportunities": [],
                    "anomalies": []}

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M").astype(str)
        df["day_of_week"] = df["date"].dt.dayofweek  # 0=Mon, 6=Sun
        df["is_weekend"] = df["day_of_week"].isin([5, 6])

        debits = df[df["transaction_type"] == "debit"].copy()

        return {
            "insights": self._behavioral_insights(debits),
            "micro_spending": self._micro_spending(debits),
            "subscriptions": self._detect_subscriptions(debits),
            "personality": self._classify_personality(df),
            "momentum": self._financial_momentum(df),
            "savings_opportunities": self._savings_opportunities(debits),
            "anomalies": self._detect_anomalies(debits),
        }

    def _behavioral_insights(self, debits: pd.DataFrame) -> list[BehavioralInsight]:
        """Generate behavioral insight cards."""
        insights = []

        if debits.empty:
            return insights

        # 1. Weekend overspending
        weekend = debits[debits["is_weekend"]]
        weekday = debits[~debits["is_weekend"]]
        if not weekend.empty and not weekday.empty:
            weekend_avg = weekend["amount"].mean()
            weekday_avg = weekday["amount"].mean()
            if weekend_avg > weekday_avg * 1.3:
                pct = round((weekend_avg - weekday_avg) / weekday_avg * 100)
                insights.append(BehavioralInsight(
                    title="Weekend Overspending",
                    description=f"You spend {pct}% more on weekends (avg ₹{weekend_avg:.0f}) vs weekdays (avg ₹{weekday_avg:.0f})",
                    severity="warning",
                    icon="📅",
                    value=f"+{pct}%",
                    recommendation="Try setting a weekend budget cap to control discretionary spending.",
                ))

        # 2. Late-night spending
        if "time_hour" in debits.columns:
            late_night = debits[debits["time_hour"].notna()]
            if not late_night.empty:
                late = late_night[late_night["time_hour"].between(22, 23) | (late_night["time_hour"].between(0, 4))]
                if len(late) >= 3:
                    late_total = late["amount"].sum()
                    insights.append(BehavioralInsight(
                        title="Late Night Spending",
                        description=f"You made {len(late)} transactions late at night, totaling ₹{late_total:.0f}",
                        severity="info",
                        icon="🌙",
                        value=f"₹{late_total:.0f}",
                        recommendation="Late-night purchases are often impulsive. Consider a 24-hour rule before buying.",
                    ))

        # 3. Spending concentration
        if "category" in debits.columns:
            cat_totals = debits.groupby("category")["amount"].sum()
            total = cat_totals.sum()
            if total > 0:
                top_cat = cat_totals.idxmax()
                top_pct = cat_totals.max() / total * 100
                if top_pct > 40:
                    insights.append(BehavioralInsight(
                        title="Spending Concentration Risk",
                        description=f"{top_pct:.0f}% of your spending is in '{top_cat}'. Heavy concentration in one category.",
                        severity="warning",
                        icon="⚠️",
                        value=f"{top_pct:.0f}%",
                        recommendation=f"Diversify spending or find ways to reduce {top_cat} costs.",
                    ))

        # 4. Transaction frequency trend
        monthly_counts = debits.groupby("month").size()
        if len(monthly_counts) >= 2:
            recent = monthly_counts.iloc[-1]
            previous = monthly_counts.iloc[-2]
            if recent > previous * 1.5:
                insights.append(BehavioralInsight(
                    title="Spending Frequency Spike",
                    description=f"Transaction count jumped from {previous} to {recent} this month.",
                    severity="warning",
                    icon="📈",
                    value=f"{recent} txns",
                    recommendation="More transactions often mean more impulse purchases. Review recent spending.",
                ))

        # 5. Average transaction size trend
        monthly_avg = debits.groupby("month")["amount"].mean()
        if len(monthly_avg) >= 2:
            recent_avg = monthly_avg.iloc[-1]
            prev_avg = monthly_avg.iloc[-2]
            if recent_avg > prev_avg * 1.3:
                insights.append(BehavioralInsight(
                    title="Rising Transaction Size",
                    description=f"Average transaction increased from ₹{prev_avg:.0f} to ₹{recent_avg:.0f}.",
                    severity="info",
                    icon="💸",
                    value=f"₹{recent_avg:.0f}",
                    recommendation="Check if this is due to necessary expenses or lifestyle inflation.",
                ))

        # 6. Dining out frequency
        if "category" in debits.columns:
            food = debits[debits["category"] == "Food & Dining"]
            if len(food) >= 10:
                avg_food_per_month = food.groupby("month").size().mean()
                if avg_food_per_month > 15:
                    insights.append(BehavioralInsight(
                        title="Frequent Dining Out",
                        description=f"You order food/dine out about {avg_food_per_month:.0f} times per month.",
                        severity="info",
                        icon="🍔",
                        value=f"{avg_food_per_month:.0f}/month",
                        recommendation="Cooking at home 5 more meals/month could save ₹2,000+",
                    ))

        return insights

    def _micro_spending(self, debits: pd.DataFrame) -> list[MicroSpendingAlert]:
        """Detect small frequent transactions that add up."""
        if debits.empty or "merchant_clean" not in debits.columns:
            return []

        # Micro = transactions under ₹200 that happen 5+ times
        micro = debits[debits["amount"] <= 200]
        merchant_freq = micro.groupby("merchant_clean").agg(
            frequency=("amount", "count"),
            total_amount=("amount", "sum"),
            avg_amount=("amount", "mean"),
            category=("category", "first"),
        )

        alerts = []
        for merchant, row in merchant_freq[merchant_freq["frequency"] >= 5].iterrows():
            alerts.append(MicroSpendingAlert(
                merchant=str(merchant),
                frequency=int(row["frequency"]),
                total_amount=round(row["total_amount"], 2),
                avg_amount=round(row["avg_amount"], 2),
                category=row["category"],
            ))

        return sorted(alerts, key=lambda x: x.total_amount, reverse=True)[:10]

    def _detect_subscriptions(self, debits: pd.DataFrame) -> list[SubscriptionItem]:
        """Detect recurring payments (subscriptions, even hidden ones)."""
        if debits.empty or "merchant_clean" not in debits.columns:
            return []

        subscriptions = []
        merchant_groups = debits.groupby("merchant_clean")

        for merchant, group in merchant_groups:
            if len(group) < 2:
                continue

            amounts = group["amount"].values
            dates = pd.to_datetime(group["date"]).sort_values()

            # Check for consistent amounts (within 10% variance)
            amount_std = np.std(amounts)
            amount_mean = np.mean(amounts)
            amount_cv = amount_std / amount_mean if amount_mean > 0 else float('inf')

            if amount_cv > 0.15:  # Too much variance
                continue

            # Check for regular intervals
            if len(dates) >= 2:
                intervals = dates.diff().dropna().dt.days.values
                if len(intervals) == 0:
                    continue

                avg_interval = np.mean(intervals)
                interval_std = np.std(intervals)

                frequency = "unknown"
                confidence = 0.0

                if 25 <= avg_interval <= 35 and interval_std < 7:
                    frequency = "monthly"
                    confidence = min(0.95, 0.6 + len(group) * 0.05)
                elif 6 <= avg_interval <= 8 and interval_std < 3:
                    frequency = "weekly"
                    confidence = min(0.95, 0.5 + len(group) * 0.03)
                elif 85 <= avg_interval <= 100 and interval_std < 15:
                    frequency = "quarterly"
                    confidence = min(0.9, 0.5 + len(group) * 0.05)
                elif 355 <= avg_interval <= 375 and interval_std < 20:
                    frequency = "yearly"
                    confidence = 0.8

                if frequency != "unknown" and confidence > 0.5:
                    is_hidden = merchant not in [
                        "Netflix", "Spotify", "Hotstar", "YouTube",
                        "Amazon", "Jio", "Airtel",
                    ]
                    subscriptions.append(SubscriptionItem(
                        merchant=str(merchant),
                        amount=round(amount_mean, 2),
                        frequency=frequency,
                        confidence=round(confidence, 2),
                        category=group["category"].mode().iloc[0] if not group["category"].mode().empty else "Subscriptions",
                        is_hidden=is_hidden,
                    ))

        return sorted(subscriptions, key=lambda x: x.amount, reverse=True)

    def _classify_personality(self, df: pd.DataFrame) -> SpendingPersonality:
        """Classify the user's spending personality."""
        debits = df[df["transaction_type"] == "debit"]
        credits = df[df["transaction_type"] == "credit"]

        total_income = credits["amount"].sum()
        total_expense = debits["amount"].sum()
        savings_rate = ((total_income - total_expense) / total_income * 100) if total_income > 0 else 0

        # Monthly spending variance
        monthly_spending = debits.groupby("month")["amount"].sum()
        spending_cv = (monthly_spending.std() / monthly_spending.mean()) if monthly_spending.mean() > 0 else 0

        # Micro-spending ratio
        micro_count = len(debits[debits["amount"] <= 200])
        micro_ratio = micro_count / len(debits) if len(debits) > 0 else 0

        # Classify
        if savings_rate > 30:
            profile = SPENDING_PERSONALITIES["saver"]
        elif spending_cv > 0.5:
            profile = SPENDING_PERSONALITIES["feast_famine"]
        elif micro_ratio > 0.5:
            profile = SPENDING_PERSONALITIES["impulse"]
        elif savings_rate < 5 and total_income > 0:
            profile = SPENDING_PERSONALITIES["lifestyle_inflator"]
        else:
            profile = SPENDING_PERSONALITIES["balanced"]

        return SpendingPersonality(
            type=profile["type"],
            description=profile["description"],
            strengths=profile["strengths"],
            risks=profile["risks"],
            icon=profile["icon"],
        )

    def _financial_momentum(self, df: pd.DataFrame) -> FinancialMomentum:
        """Track whether financial habits are improving or worsening."""
        debits = df[df["transaction_type"] == "debit"]
        monthly = debits.groupby("month")["amount"].sum().sort_index()

        if len(monthly) < 3:
            return FinancialMomentum(
                direction="stable",
                score=0.0,
                description="Not enough data to determine momentum (need 3+ months).",
                factors=["Insufficient data"],
            )

        # Linear trend on monthly spending
        values = monthly.values
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]
        avg = np.mean(values)

        # Normalize slope relative to average
        normalized_slope = slope / avg if avg > 0 else 0
        score = max(-1, min(1, -normalized_slope * 10))  # Negative slope = improving

        factors = []
        if score > 0.3:
            direction = "improving"
            factors.append("Spending is trending downward")
        elif score < -0.3:
            direction = "declining"
            factors.append("Spending is trending upward")
        else:
            direction = "stable"
            factors.append("Spending is relatively consistent")

        # Check most recent month vs average
        recent = values[-1]
        if recent < avg * 0.9:
            factors.append("Last month was below average — great job!")
        elif recent > avg * 1.1:
            factors.append("Last month was above average — watch out")

        descriptions = {
            "improving": "Your financial habits are getting stronger. Keep it up!",
            "stable": "Your spending is consistent. Look for optimization opportunities.",
            "declining": "Your spending trend is rising. Time to review and adjust.",
        }

        return FinancialMomentum(
            direction=direction,
            score=round(score, 2),
            description=descriptions[direction],
            factors=factors,
        )

    def _savings_opportunities(self, debits: pd.DataFrame) -> list[SavingsOpportunity]:
        """Identify categories where the user can save money."""
        if debits.empty or "category" not in debits.columns:
            return []

        cat_totals = debits.groupby("category")["amount"].sum().sort_values(ascending=False)
        total = cat_totals.sum()

        opportunities = []
        reduction_suggestions = {
            "Food & Dining": ("Cook more meals at home", "easy", 0.3),
            "Shopping": ("Implement a 48-hour rule before purchases", "moderate", 0.25),
            "Entertainment": ("Audit and cancel unused subscriptions", "easy", 0.2),
            "Transport": ("Use public transport or carpool", "moderate", 0.2),
            "Subscriptions": ("Review and cancel unused subscriptions", "easy", 0.5),
            "Personal Care": ("Space out appointments", "easy", 0.15),
        }

        for cat, amount in cat_totals.items():
            if cat in reduction_suggestions:
                suggestion, difficulty, reduction = reduction_suggestions[cat]
                potential = amount * reduction
                if potential > 500:  # Only suggest if meaningful savings
                    opportunities.append(SavingsOpportunity(
                        category=str(cat),
                        current_spend=round(amount, 2),
                        potential_saving=round(potential, 2),
                        difficulty=difficulty,
                        suggestion=suggestion,
                    ))

        return sorted(opportunities, key=lambda x: x.potential_saving, reverse=True)[:5]

    def _detect_anomalies(self, debits: pd.DataFrame) -> list[AnomalyItem]:
        """Detect unusual transactions using statistical methods."""
        if debits.empty:
            return []

        anomalies = []
        
        # Method 1: Category-level anomalies (transactions > 2 std devs from category mean)
        if "category" in debits.columns:
            for cat, group in debits.groupby("category"):
                if len(group) < 5:
                    continue
                mean = group["amount"].mean()
                std = group["amount"].std()
                if std == 0:
                    continue

                threshold = mean + 2 * std
                outliers = group[group["amount"] > threshold]

                for _, row in outliers.iterrows():
                    z_score = (row["amount"] - mean) / std
                    anomalies.append(AnomalyItem(
                        date=str(row["date"])[:10],
                        description=row.get("description_clean", row.get("description", "Unknown")),
                        amount=round(row["amount"], 2),
                        category=str(cat),
                        reason=f"Amount is {z_score:.1f}x standard deviations above the '{cat}' average of ₹{mean:.0f}",
                        severity="high" if z_score > 3 else "medium",
                    ))

        # Method 2: Overall large transactions (top 1% by amount)
        if len(debits) >= 20:
            threshold_99 = debits["amount"].quantile(0.99)
            large_txns = debits[debits["amount"] >= threshold_99]
            for _, row in large_txns.iterrows():
                already_flagged = any(
                    a.date == str(row["date"])[:10] and a.amount == round(row["amount"], 2)
                    for a in anomalies
                )
                if not already_flagged:
                    anomalies.append(AnomalyItem(
                        date=str(row["date"])[:10],
                        description=row.get("description_clean", row.get("description", "Unknown")),
                        amount=round(row["amount"], 2),
                        category=row.get("category", "Unknown"),
                        reason="This is one of your largest transactions ever",
                        severity="medium",
                    ))

        return sorted(anomalies, key=lambda x: x.amount, reverse=True)[:10]
