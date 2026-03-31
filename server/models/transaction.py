"""Transaction model — stores cleaned, masked transaction data."""
import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    time_hour: Mapped[int] = mapped_column(Integer, nullable=True)  # 0-23 for behavioral analysis
    description_masked: Mapped[str] = mapped_column(String(500))
    description_clean: Mapped[str] = mapped_column(String(300))
    amount: Mapped[float] = mapped_column(Float)
    transaction_type: Mapped[str] = mapped_column(String(10))  # credit / debit
    category: Mapped[str] = mapped_column(String(100), default="Uncategorized")
    merchant_clean: Mapped[str] = mapped_column(String(200), nullable=True)
    original_hash: Mapped[str] = mapped_column(String(64))  # SHA256 of original row for dedup
    is_recurring: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
