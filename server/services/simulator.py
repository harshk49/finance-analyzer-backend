"""What-If Simulator — project savings under reduction scenarios.

Features:
  • Per-category reduction scenarios (custom % or flat ₹ amount)
  • Multi-scenario comparison
  • Auto-generates sensible defaults from actual spending data
  • Cumulative projections (3, 6, 12 months)
  • Combined scenario stacking (reduce multiple categories at once)
"""
import logging
from typing import Optional

import pandas as pd

from server.schemas.analytics import WhatIfResult

logger = logging.getLogger(__name__)


class WhatIfSimulator:
    """Simulate savings under different spending reduction scenarios."""

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def simulate(
        self,
        transactions: list[dict],
        scenarios: Optional[list[dict]] = None,
    ) -> dict:
        """Run what-if simulations.

        Parameters
        ----------
        transactions : list[dict]
            Structured transactions.
        scenarios : list[dict], optional
            Each: ``{"category": "Food & Dining", "reduction_pct": 20}``
            or ``{"category": "Shopping", "reduction_amount": 2000}``
            Use ``"category": "all"`` for overall reduction.
            If None, auto-generates smart defaults.

        Returns
        -------
        dict with keys:
            individual_scenarios  – per-scenario results
            combined_scenario     – result when ALL reductions are applied together
            summary               – aggregate stats
        """
        if not transactions:
            return self._empty_result()

        df = pd.DataFrame(transactions)
        df["date"] = pd.to_datetime(df["date"])
        debits = df[df["transaction_type"] == "debit"].copy()

        if debits.empty:
            return self._empty_result()

        # Calculate months of data
        date_range = (df["date"].max() - df["date"].min()).days / 30.44
        months = max(date_range, 1)

        total_monthly = float(debits["amount"].sum() / months)

        # Category monthly breakdown
        cat_monthly = {}
        if "category" in debits.columns:
            for cat, group in debits.groupby("category"):
                cat_monthly[str(cat)] = float(group["amount"].sum() / months)

        # Default scenarios if none provided
        if not scenarios:
            scenarios = self._generate_default_scenarios(debits, cat_monthly)

        # ── Individual scenarios ────────────────────────────────────
        individual = []
        for scenario in scenarios:
            result = self._run_scenario(scenario, total_monthly, cat_monthly, months)
            if result:
                individual.append(result)

        individual.sort(key=lambda x: x["yearly_savings"], reverse=True)

        # ── Combined scenario (all reductions stacked) ─────────────
        combined = self._run_combined(scenarios, total_monthly, cat_monthly)

        # ── Summary ─────────────────────────────────────────────────
        summary = {
            "current_monthly_spend": round(total_monthly, 2),
            "scenarios_analyzed": len(individual),
            "max_yearly_savings": round(individual[0]["yearly_savings"], 2) if individual else 0,
            "combined_yearly_savings": round(combined["yearly_savings"], 2) if combined else 0,
        }

        return {
            "individual_scenarios": individual,
            "combined_scenario": combined,
            "summary": summary,
        }

    # ────────────────────────────────────────────────────────────────
    # Legacy API (backward compat with old router)
    # ────────────────────────────────────────────────────────────────

    def simulate_legacy(
        self,
        transactions: list[dict],
        scenarios: list[dict] = None,
    ) -> list[WhatIfResult]:
        """Old-style flat list of WhatIfResult for backward compat."""
        result = self.simulate(transactions, scenarios)
        return [
            WhatIfResult(
                scenario=s["label"],
                current_monthly=s["current_monthly"],
                projected_monthly=s["projected_monthly"],
                monthly_savings=s["monthly_savings"],
                yearly_savings=s["yearly_savings"],
            )
            for s in result.get("individual_scenarios", [])
        ]

    # ────────────────────────────────────────────────────────────────
    # Single scenario
    # ────────────────────────────────────────────────────────────────

    def _run_scenario(
        self,
        scenario: dict,
        total_monthly: float,
        cat_monthly: dict[str, float],
        months: float,
    ) -> Optional[dict]:
        """Evaluate a single scenario."""
        category = scenario.get("category", "all")
        reduction_pct = scenario.get("reduction_pct", 0)
        reduction_amount = scenario.get("reduction_amount", 0)

        if category.lower() == "all":
            current = total_monthly
            if reduction_pct:
                reduced = current * (1 - reduction_pct / 100)
                label = f"Reduce all spending by {reduction_pct}%"
            elif reduction_amount:
                reduced = max(0, current - reduction_amount)
                label = f"Cut ₹{reduction_amount:,.0f}/month from total spending"
            else:
                return None
        else:
            cat_spend = cat_monthly.get(category, 0)
            if cat_spend == 0:
                return None

            if reduction_pct:
                saving = cat_spend * reduction_pct / 100
                label = f"Reduce {category} by {reduction_pct}%"
            elif reduction_amount:
                saving = min(reduction_amount, cat_spend)
                label = f"Cut ₹{reduction_amount:,.0f}/month from {category}"
            else:
                return None

            reduced = total_monthly - saving
            current = total_monthly

        monthly_savings = current - reduced

        return {
            "label": label,
            "category": category,
            "reduction_pct": reduction_pct,
            "reduction_amount": reduction_amount,
            "current_monthly": round(current, 2),
            "projected_monthly": round(reduced, 2),
            "monthly_savings": round(monthly_savings, 2),
            "yearly_savings": round(monthly_savings * 12, 2),
            "projections": {
                "3_months": round(monthly_savings * 3, 2),
                "6_months": round(monthly_savings * 6, 2),
                "12_months": round(monthly_savings * 12, 2),
            },
            "category_current": round(cat_monthly.get(category, total_monthly), 2),
        }

    # ────────────────────────────────────────────────────────────────
    # Combined scenario
    # ────────────────────────────────────────────────────────────────

    def _run_combined(
        self,
        scenarios: list[dict],
        total_monthly: float,
        cat_monthly: dict[str, float],
    ) -> dict:
        """Run all scenarios combined (stacked reductions)."""
        total_savings = 0.0
        applied_scenarios = []

        for scenario in scenarios:
            category = scenario.get("category", "all")
            reduction_pct = scenario.get("reduction_pct", 0)
            reduction_amount = scenario.get("reduction_amount", 0)

            if category.lower() == "all":
                saving = total_monthly * reduction_pct / 100 if reduction_pct else reduction_amount
            else:
                cat_spend = cat_monthly.get(category, 0)
                if cat_spend == 0:
                    continue
                if reduction_pct:
                    saving = cat_spend * reduction_pct / 100
                elif reduction_amount:
                    saving = min(reduction_amount, cat_spend)
                else:
                    continue

            total_savings += saving
            applied_scenarios.append({
                "category": category,
                "monthly_saving": round(saving, 2),
            })

        projected = max(0, total_monthly - total_savings)

        return {
            "label": "All reductions combined",
            "current_monthly": round(total_monthly, 2),
            "projected_monthly": round(projected, 2),
            "monthly_savings": round(total_savings, 2),
            "yearly_savings": round(total_savings * 12, 2),
            "projections": {
                "3_months": round(total_savings * 3, 2),
                "6_months": round(total_savings * 6, 2),
                "12_months": round(total_savings * 12, 2),
            },
            "breakdown": applied_scenarios,
        }

    # ────────────────────────────────────────────────────────────────
    # Auto-generate scenarios
    # ────────────────────────────────────────────────────────────────

    def _generate_default_scenarios(
        self,
        debits: pd.DataFrame,
        cat_monthly: dict[str, float],
    ) -> list[dict]:
        """Generate smart default scenarios based on actual spending."""
        scenarios = [{"category": "all", "reduction_pct": 10}]

        # Skip non-reducible categories
        skip_cats = {"Transfer", "EMI & Loans", "Rent & Housing", "Salary", "Interest", "Refund"}

        # Sort categories by monthly spend
        reducible = [
            (cat, spend) for cat, spend in cat_monthly.items()
            if cat not in skip_cats and spend > 0
        ]
        reducible.sort(key=lambda x: x[1], reverse=True)

        # Top categories get 20% reduction scenarios
        for cat, spend in reducible[:5]:
            scenarios.append({"category": cat, "reduction_pct": 20})

        return scenarios[:7]

    @staticmethod
    def _empty_result() -> dict:
        return {
            "individual_scenarios": [],
            "combined_scenario": {},
            "summary": {
                "current_monthly_spend": 0,
                "scenarios_analyzed": 0,
                "max_yearly_savings": 0,
                "combined_yearly_savings": 0,
            },
        }
