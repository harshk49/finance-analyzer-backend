"""FastAPI application entry point.

AI Personal Finance Analyzer — Privacy-first financial analytics platform.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import ALLOWED_ORIGINS
from server.routers import upload, analytics, insights

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle events."""
    logger.info("🚀 AI Personal Finance Analyzer starting...")
    logger.info(f"📊 CORS allowed origins: {ALLOWED_ORIGINS}")
    yield
    logger.info("👋 Shutting down...")


app = FastAPI(
    title="AI Personal Finance Analyzer",
    description=(
        "Privacy-first financial analytics platform. "
        "Upload bank statement CSVs to receive intelligent insights about "
        "spending behavior, financial habits, and future projections."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(upload.router)
app.include_router(analytics.router)
app.include_router(insights.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "AI Personal Finance Analyzer",
        "version": "1.0.0",
    }
