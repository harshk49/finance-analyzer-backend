"""Insights router — behavioral insights, momentum, simulations, etc.

Endpoints for the Insights tab of the frontend dashboard.
"""
from typing import Optional

from fastapi import APIRouter, Query

from server.routers.upload import get_session_transactions
from server.services.insights_engine import InsightsEngine
from server.services.behavior_insights import BehaviorInsightsEngine
from server.services.monthly_summary import MonthlySummaryEngine
from server.services.financial_momentum import FinancialMomentumEngine
from server.services.micro_spend_detector import MicroSpendDetector
from server.services.subscription_detector import SubscriptionDetector
from server.services.simulator import WhatIfSimulator
from server.services.savings_ranker import SavingsOpportunityRanker
from server.services.forecast_engine import ForecastEngine
from server.services.story_generator import StoryGenerator

router = APIRouter(prefix="/api/insights", tags=["Insights"])

insights_engine = InsightsEngine()
behavior_engine = BehaviorInsightsEngine()
monthly_engine = MonthlySummaryEngine()
momentum_engine = FinancialMomentumEngine()
micro_detector = MicroSpendDetector()
subscription_detector = SubscriptionDetector()
simulator = WhatIfSimulator()
savings_ranker = SavingsOpportunityRanker()
forecast_engine = ForecastEngine()
story_generator = StoryGenerator()


@router.get("/behavioral")
async def get_behavioral_insights(session_token: str = Query(...)):
    """Get all behavioral insights including personality, momentum, etc."""
    transactions = get_session_transactions(session_token)
    return insights_engine.generate_all(transactions)


@router.get("/behavior-patterns")
async def get_behavior_patterns(session_token: str = Query(...)):
    """Detailed behavioral spending patterns.

    Returns day-of-week breakdown, time-of-day heatmap,
    weekend overspending, and late-night detection.
    """
    transactions = get_session_transactions(session_token)
    return behavior_engine.analyze(transactions)


@router.get("/monthly-summary")
async def get_monthly_summary(
    session_token: str = Query(...),
    month: Optional[str] = Query(None, description="Target month (YYYY-MM)"),
):
    """Monthly financial summaries with month-over-month comparisons."""
    transactions = get_session_transactions(session_token)
    return monthly_engine.summarize(transactions, target_month=month)


@router.get("/momentum")
async def get_financial_momentum(session_token: str = Query(...)):
    """Financial momentum analysis.

    Composite score (-100 to +100), spending/savings trends with
    rolling averages, and per-category momentum direction.
    """
    transactions = get_session_transactions(session_token)
    return momentum_engine.analyze(transactions)


@router.get("/micro-spending")
async def get_micro_spending(
    session_token: str = Query(...),
    threshold: float = Query(300.0, ge=50, le=1000),
):
    """Detect small transactions that silently drain money."""
    transactions = get_session_transactions(session_token)
    detector = MicroSpendDetector(threshold=threshold)
    return detector.analyze(transactions)


@router.get("/subscriptions")
async def get_subscriptions(session_token: str = Query(...)):
    """Detect recurring payments (known + hidden subscriptions)."""
    transactions = get_session_transactions(session_token)
    return subscription_detector.detect(transactions)


@router.post("/simulate")
async def run_simulation(
    session_token: str = Query(...),
    scenarios: Optional[list[dict]] = None,
):
    """What-if simulator — project savings under reduction scenarios.

    Body: [{"category": "Food & Dining", "reduction_pct": 20}]
    Supports both % reduction and flat ₹ reduction.
    Returns individual + combined scenario results.
    """
    transactions = get_session_transactions(session_token)
    return simulator.simulate(transactions, scenarios)


@router.get("/savings-opportunities")
async def get_savings_opportunities(session_token: str = Query(...)):
    """Rank spending categories by saving potential.

    Uses opportunity scoring (spend × reduction potential × inverse difficulty)
    with 3-level projections and quick-win identification.
    """
    transactions = get_session_transactions(session_token)
    return savings_ranker.rank(transactions)


@router.get("/forecast")
async def get_forecast(
    session_token: str = Query(...),
    months: int = Query(3, ge=1, le=12),
):
    """Get spending forecast for the next N months."""
    transactions = get_session_transactions(session_token)
    return forecast_engine.forecast(transactions, months)


@router.get("/story")
async def get_financial_story(
    session_token: str = Query(...),
    month: Optional[str] = Query(None),
):
    """Get a human-readable financial story for a given month."""
    transactions = get_session_transactions(session_token)
    return story_generator.generate(transactions, month)
