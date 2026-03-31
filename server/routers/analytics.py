"""Analytics router — financial dashboard data endpoints."""
from typing import Optional

from fastapi import APIRouter, Query

from server.routers.upload import get_session_transactions
from server.services.analytics_engine import AnalyticsEngine
from server.schemas.analytics import AnalyticsSummary
from server.schemas.transaction import TransactionListResponse, TransactionOut

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

analytics_engine = AnalyticsEngine()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(session_token: str = Query(...)):
    """Get complete analytics summary for a session."""
    transactions = get_session_transactions(session_token)
    return analytics_engine.compute(transactions)


@router.get("/extended")
async def get_extended_analytics(session_token: str = Query(...)):
    """Get extended analytics with category trends, rolling averages,
    daily cash flow, and top merchants.

    Returns a richer, more detailed dataset than /summary.
    """
    transactions = get_session_transactions(session_token)
    return analytics_engine.compute_extended(transactions)


@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    session_token: str = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    category: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
):
    """Get paginated transaction list with optional filters."""
    transactions = get_session_transactions(session_token)

    # Filters
    filtered = transactions
    if category:
        filtered = [t for t in filtered if t.get("category") == category]
    if transaction_type:
        filtered = [t for t in filtered if t.get("transaction_type") == transaction_type]

    # Sort by date descending
    filtered = sorted(filtered, key=lambda x: str(x.get("date", "")), reverse=True)

    # Paginate
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    return TransactionListResponse(
        transactions=[
            TransactionOut(
                id=str(i),
                date=t["date"],
                time_hour=t.get("time_hour"),
                description_clean=t.get("description_clean", t.get("merchant_clean", "Unknown")),
                amount=t["amount"],
                transaction_type=t["transaction_type"],
                category=t.get("category", "Uncategorized"),
                merchant_clean=t.get("merchant_clean"),
                is_recurring=t.get("is_recurring", False),
            )
            for i, t in enumerate(page_items, start=start)
        ],
        total=total,
        page=page,
        per_page=per_page,
    )
