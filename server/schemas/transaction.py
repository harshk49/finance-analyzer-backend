"""Transaction Pydantic schemas."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    date: date
    time_hour: Optional[int] = None
    description_masked: str
    description_clean: str
    amount: float
    transaction_type: str  # credit / debit
    category: str = "Uncategorized"
    merchant_clean: Optional[str] = None
    original_hash: str
    is_recurring: bool = False


class TransactionOut(BaseModel):
    id: str
    date: date
    time_hour: Optional[int]
    description_clean: str
    amount: float
    transaction_type: str
    category: str
    merchant_clean: Optional[str]
    is_recurring: bool

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    transactions: list[TransactionOut]
    total: int
    page: int = 1
    per_page: int = 50
