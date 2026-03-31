"""FastAPI application entry point.

AI Personal Finance Analyzer — Privacy-first financial analytics platform.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from server.config import ALLOWED_ORIGINS, APP_ENV, DEBUG, LOG_LEVEL
from server.database import init_db
from server.routers import upload, analytics, insights

# ── Logging ────────────────────────────────────────────
log_format = (
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    if APP_ENV == "development"
    else '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
)
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format=log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle events."""
    logger.info("🚀 AI Personal Finance Analyzer starting (env=%s)...", APP_ENV)
    logger.info("📊 CORS allowed origins: %s", ALLOWED_ORIGINS)

    # Auto-create tables on first boot (safe: create_all is idempotent)
    try:
        await init_db()
        logger.info("✅ Database tables verified / created.")
    except Exception as exc:
        logger.error("❌ Database init failed: %s", exc)
        # Don't crash — Azure health probes will report unhealthy

    yield
    logger.info("👋 Shutting down...")


# ── App factory ────────────────────────────────────────
is_production = APP_ENV == "production"

app = FastAPI(
    title="AI Personal Finance Analyzer",
    description=(
        "Privacy-first financial analytics platform. "
        "Upload bank statement CSVs to receive intelligent insights about "
        "spending behavior, financial habits, and future projections."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # Disable interactive docs in production
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

# ── Middleware (order matters — outermost first) ───────

# Trusted hosts — prevent host-header attacks in production
if is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.azurewebsites.net", "*.azure.com", "localhost"],
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    start = time.time()
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Request-ID"] = request.headers.get(
        "x-request-id", f"{time.time_ns()}"
    )
    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    # Log request duration
    duration = round(time.time() - start, 4)
    logger.debug("%s %s → %s (%.4fs)", request.method, request.url.path, response.status_code, duration)
    return response


# ── Routers ────────────────────────────────────────────
app.include_router(upload.router)
app.include_router(analytics.router)
app.include_router(insights.router)


# ── Health check ───────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Health check endpoint used by Azure App Service probes."""
    return {
        "status": "healthy",
        "service": "AI Personal Finance Analyzer",
        "version": "1.0.0",
        "environment": APP_ENV,
    }
