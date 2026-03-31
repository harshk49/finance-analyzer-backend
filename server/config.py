"""Application configuration using environment variables.

Loads settings from .env file via python-dotenv, falling back to
sensible defaults for local development.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── Paths ──────────────────────────────────────────
UPLOAD_DIR = BASE_DIR / "temp_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── Database ───────────────────────────────────────
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "finance_analyzer")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)
DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

# ── Security ───────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
SESSION_EXPIRY_HOURS = int(os.getenv("SESSION_EXPIRY_HOURS", "24"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))

# ── CORS ───────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

# ── App ────────────────────────────────────────────
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── ML ─────────────────────────────────────────────
ML_MODEL_PATH = BASE_DIR / "server" / "ml" / "trained_models"
