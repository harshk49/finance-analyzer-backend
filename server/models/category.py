"""Category model — predefined spending categories."""
import uuid
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import ARRAY
from server.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    icon: Mapped[str] = mapped_column(String(10), default="💰")
    keywords: Mapped[list] = mapped_column(ARRAY(String), default=list)
    parent_category: Mapped[str] = mapped_column(String(100), nullable=True)
