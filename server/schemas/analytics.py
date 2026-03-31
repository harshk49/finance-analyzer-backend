"""Analytics response schemas."""
from typing import Optional
from pydantic import BaseModel


class CategoryBreakdown(BaseModel):
    category: str
    total: float
    percentage: float
    count: int
    icon: str = "💰"


class MonthlySpending(BaseModel):
    month: str  # "2024-01"
    total_debit: float
    total_credit: float
    net: float
    transaction_count: int


class CashFlowData(BaseModel):
    month: str
    income: float
    expenses: float
    net: float


class TrendData(BaseModel):
    period: str
    value: float
    change_pct: Optional[float] = None


class BehavioralInsight(BaseModel):
    title: str
    description: str
    severity: str  # info, warning, critical
    icon: str
    value: Optional[str] = None
    recommendation: str


class MicroSpendingAlert(BaseModel):
    merchant: str
    frequency: int
    total_amount: float
    avg_amount: float
    category: str


class SubscriptionItem(BaseModel):
    merchant: str
    amount: float
    frequency: str  # monthly, weekly, quarterly
    confidence: float
    category: str
    is_hidden: bool = False


class SpendingPersonality(BaseModel):
    type: str
    description: str
    strengths: list[str]
    risks: list[str]
    icon: str


class AnomalyItem(BaseModel):
    date: str
    description: str
    amount: float
    category: str
    reason: str
    severity: str  # low, medium, high


class ForecastData(BaseModel):
    month: str
    predicted_spending: float
    lower_bound: float
    upper_bound: float
    confidence: float


class WhatIfResult(BaseModel):
    scenario: str
    current_monthly: float
    projected_monthly: float
    monthly_savings: float
    yearly_savings: float


class FinancialMomentum(BaseModel):
    direction: str  # improving, stable, declining
    score: float  # -1 to 1
    description: str
    factors: list[str]


class SavingsOpportunity(BaseModel):
    category: str
    current_spend: float
    potential_saving: float
    difficulty: str  # easy, moderate, hard
    suggestion: str


class FinancialStory(BaseModel):
    title: str
    month: str
    summary: str
    highlights: list[str]
    concerns: list[str]
    tips: list[str]
    score: float  # 0-100 financial health score


class AnalyticsSummary(BaseModel):
    total_income: float
    total_expenses: float
    net_savings: float
    savings_rate: float
    avg_daily_spend: float
    top_category: str
    transaction_count: int
    date_range: dict  # {start, end}
    monthly_spending: list[MonthlySpending]
    category_breakdown: list[CategoryBreakdown]
    cash_flow: list[CashFlowData]
    trends: list[TrendData]
