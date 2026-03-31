"""Savings Opportunity Ranker — data-driven savings potential analysis.

Ranks spending categories by saving potential using:
  • Current spending vs national/category benchmarks
  • Reduction difficulty per category
  • Merchant-level actionable breakdowns
  • Projected savings at 10% / 20% / 30% reduction levels
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

from server.utils.constants import CATEGORY_ICONS

logger = logging.getLogger(__name__)

# ── Category metadata (difficulty, typical reduction potential) ──────
# difficulty: how hard it is to reduce spending in this category
# base_reduction: conservative recommended % reduction
# description: why this category is reducible
_CATEGORY_META: dict[str, dict] = {
    "Food & Dining": {
        "difficulty": "easy",
        "difficulty_score": 1,
        "base_reduction": 0.25,
        "tip": "Cook at home more, batch-order instead of individual orders",
    },
    "Shopping": {
        "difficulty": "moderate",
        "difficulty_score": 2,
        "base_reduction": 0.20,
        "tip": "Implement a 48-hour rule before non-essential purchases",
    },
    "Entertainment": {
        "difficulty": "easy",
        "difficulty_score": 1,
        "base_reduction": 0.30,
        "tip": "Audit subscriptions and cancel the unused ones",
    },
    "Subscriptions": {
        "difficulty": "easy",
        "difficulty_score": 1,
        "base_reduction": 0.40,
        "tip": "Cancel unused subscriptions — most people have 2-3 they don't use",
    },
    "Transport": {
        "difficulty": "moderate",
        "difficulty_score": 2,
        "base_reduction": 0.15,
        "tip": "Use public transport or carpool 2-3 days a week",
    },
    "Groceries": {
        "difficulty": "moderate",
        "difficulty_score": 2,
        "base_reduction": 0.15,
        "tip": "Plan meals weekly, avoid impulse buys, use a shopping list",
    },
    "Personal Care": {
        "difficulty": "easy",
        "difficulty_score": 1,
        "base_reduction": 0.15,
        "tip": "Space out appointments and look for bundled deals",
    },
    "Health & Medical": {
        "difficulty": "hard",
        "difficulty_score": 3,
        "base_reduction": 0.05,
        "tip": "Use generic medicines, compare pharmacy prices",
    },
    "Bills & Utilities": {
        "difficulty": "moderate",
        "difficulty_score": 2,
        "base_reduction": 0.10,
        "tip": "Switch to annual plans, negotiate rates, reduce usage",
    },
    "Education": {
        "difficulty": "hard",
        "difficulty_score": 3,
        "base_reduction": 0.05,
        "tip": "Look for free alternatives, scholarships, or group discounts",
    },
}

# Categories that should NOT be ranked for savings
_SKIP_CATEGORIES = {
    "Salary", "Transfer", "EMI & Loans", "Rent & Housing",
    "Interest", "Refund", "Investment", "ATM & Cash", "Uncategorized",
}


class SavingsOpportunityRanker:
    """Rank spending categories by saving potential."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def rank(self, transactions: list[dict]) -> dict:
        """Rank categories by savings opportunity.

        Returns
        -------
        dict with keys:
            opportunities   – ranked list of saving opportunities
            summary         – aggregate stats
            quick_wins      – easiest + highest-impact items
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        debits = df[df["transaction_type"] == "debit"].copy()

        if debits.empty or "category" not in debits.columns:
            return self._empty_result()

        # Calculate months
        date_range = (df["date"].max() - df["date"].min()).days / 30.44
        months = max(date_range, 1)

        total_monthly = float(debits["amount"].sum() / months)

        opportunities = self._analyze_categories(debits, months, total_monthly)
        quick_wins = self._find_quick_wins(opportunities)
        summary = self._compute_summary(opportunities, total_monthly)

        return {
            "opportunities": opportunities,
            "quick_wins": quick_wins,
            "summary": summary,
        }

    # ────────────────────────────────────────────────────────────────
    # Category analysis
    # ────────────────────────────────────────────────────────────────

    def _analyze_categories(
        self, debits: pd.DataFrame, months: float, total_monthly: float,
    ) -> list[dict]:
        """Analyze each category for saving potential."""

        cat_agg = debits.groupby("category").agg(
            total=("amount", "sum"),
            count=("amount", "count"),
            avg=("amount", "mean"),
        ).sort_values("total", ascending=False)

        opportunities = []

        for cat, row in cat_agg.iterrows():
            cat_str = str(cat)
            if cat_str in _SKIP_CATEGORIES:
                continue

            monthly_spend = float(row["total"]) / months
            pct_of_total = round(monthly_spend / total_monthly * 100, 1) if total_monthly > 0 else 0

            # Get category metadata
            meta = _CATEGORY_META.get(cat_str, {
                "difficulty": "moderate",
                "difficulty_score": 2,
                "base_reduction": 0.10,
                "tip": "Review and find areas to cut back",
            })

            base_reduction = meta["base_reduction"]

            # ── Savings projections at different levels ──────────
            projections = {
                "conservative_10pct": {
                    "monthly": round(monthly_spend * 0.10, 2),
                    "yearly": round(monthly_spend * 0.10 * 12, 2),
                },
                "moderate_20pct": {
                    "monthly": round(monthly_spend * 0.20, 2),
                    "yearly": round(monthly_spend * 0.20 * 12, 2),
                },
                "aggressive_30pct": {
                    "monthly": round(monthly_spend * 0.30, 2),
                    "yearly": round(monthly_spend * 0.30 * 12, 2),
                },
                "recommended": {
                    "monthly": round(monthly_spend * base_reduction, 2),
                    "yearly": round(monthly_spend * base_reduction * 12, 2),
                    "reduction_pct": round(base_reduction * 100),
                },
            }

            # ── Top merchants in this category ──────────────
            top_merchants = []
            if "merchant_clean" in debits.columns:
                cat_df = debits[debits["category"] == cat_str]
                merch = cat_df.groupby("merchant_clean")["amount"].agg(["sum", "count"])
                merch = merch.sort_values("sum", ascending=False).head(3)
                for m, mr in merch.iterrows():
                    top_merchants.append({
                        "merchant": str(m),
                        "monthly_spend": round(float(mr["sum"]) / months, 2),
                        "count": int(mr["count"]),
                    })

            # ── Opportunity score (higher = better opportunity) ──
            # Weighted: higher spend + easier difficulty = better opportunity
            difficulty_multiplier = {1: 1.5, 2: 1.0, 3: 0.5}
            opp_score = round(
                monthly_spend * base_reduction * difficulty_multiplier.get(meta["difficulty_score"], 1),
                2,
            )

            opportunities.append({
                "rank": 0,  # filled below
                "category": cat_str,
                "icon": CATEGORY_ICONS.get(cat_str, "💰"),
                "monthly_spend": round(monthly_spend, 2),
                "pct_of_total_spend": pct_of_total,
                "transaction_count": int(row["count"]),
                "avg_transaction": round(float(row["avg"]), 2),
                "difficulty": meta["difficulty"],
                "difficulty_score": meta["difficulty_score"],
                "tip": meta["tip"],
                "projections": projections,
                "top_merchants": top_merchants,
                "opportunity_score": opp_score,
            })

        # Sort by opportunity score
        opportunities.sort(key=lambda o: o["opportunity_score"], reverse=True)

        # Assign ranks
        for i, opp in enumerate(opportunities):
            opp["rank"] = i + 1

        return opportunities

    # ────────────────────────────────────────────────────────────────
    # Quick wins
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_quick_wins(opportunities: list[dict]) -> list[dict]:
        """Find the easiest, highest-impact savings opportunities."""
        easy = [o for o in opportunities if o["difficulty"] == "easy" and o["monthly_spend"] > 200]
        easy.sort(key=lambda o: o["projections"]["recommended"]["yearly"], reverse=True)

        return [
            {
                "category": o["category"],
                "icon": o["icon"],
                "tip": o["tip"],
                "monthly_spend": o["monthly_spend"],
                "potential_monthly_saving": o["projections"]["recommended"]["monthly"],
                "potential_yearly_saving": o["projections"]["recommended"]["yearly"],
            }
            for o in easy[:3]
        ]

    # ────────────────────────────────────────────────────────────────
    # Summary
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_summary(opportunities: list[dict], total_monthly: float) -> dict:
        """Aggregate savings summary."""
        if not opportunities:
            return {
                "total_monthly_spend_analyzed": 0,
                "total_categories": 0,
                "recommended_monthly_saving": 0,
                "recommended_yearly_saving": 0,
                "max_monthly_saving": 0,
                "max_yearly_saving": 0,
            }

        rec_monthly = sum(o["projections"]["recommended"]["monthly"] for o in opportunities)
        agg_monthly = sum(o["projections"]["aggressive_30pct"]["monthly"] for o in opportunities)
        analyzed_spend = sum(o["monthly_spend"] for o in opportunities)

        return {
            "total_monthly_spend_analyzed": round(analyzed_spend, 2),
            "total_monthly_spend": round(total_monthly, 2),
            "total_categories": len(opportunities),
            "recommended_monthly_saving": round(rec_monthly, 2),
            "recommended_yearly_saving": round(rec_monthly * 12, 2),
            "max_monthly_saving": round(agg_monthly, 2),
            "max_yearly_saving": round(agg_monthly * 12, 2),
            "recommended_saving_pct": round(rec_monthly / total_monthly * 100, 1) if total_monthly > 0 else 0,
        }

    @staticmethod
    def _empty_result() -> dict:
        return {"opportunities": [], "quick_wins": [], "summary": {}}
