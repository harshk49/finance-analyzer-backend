"""Database connection and session management.

Uses SQLAlchemy async engine with PostgreSQL.
Falls back to SQLite for development/testing.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from server.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db():
    """Dependency: yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Create all tables (development only)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
