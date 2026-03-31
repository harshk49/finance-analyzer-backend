"""User model — session-based, minimal data storage."""
import uuid
from datetime import datetime, timedelta
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from server.database import Base
from server.config import SESSION_EXPIRY_HOURS


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=SESSION_EXPIRY_HOURS),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
