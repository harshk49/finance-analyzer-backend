"""Transaction Structurer — converts cleaned dicts into the standard JSON schema.

This is the *last mile* before data hits the API response or the database.
It guarantees every transaction has:
  • ``id``               – deterministic UUID-5 from original_hash
  • ``date``             – ISO 8601 string  (yyyy-mm-dd)
  • ``amount``           – positive float, 2 decimal places
  • ``transaction_type`` – ``"credit"`` | ``"debit"``
  • ``category``         – string, default ``"Uncategorized"``
  • ``merchant_clean``   – cleaned merchant name
  • ``description_clean``– cleaned description (= merchant_clean by default)
  • ``description_masked``– original desc with sensitive data masked
  • ``original_hash``    – SHA-256 of the raw CSV row
  • ``time_hour``        – int 0-23 or null
  • ``is_recurring``     – bool, default False  (filled later by insights engine)
  • ``metadata``         – dict for extensibility (raw_description, etc.)
"""
import logging
import uuid
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Deterministic UUID-5 namespace for transaction IDs
_TXN_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")

# Allowed transaction types
_VALID_TYPES = {"credit", "debit"}


def structure_transaction(raw: dict) -> dict:
    """Convert a single cleaned transaction dict into the standard schema.

    Parameters
    ----------
    raw : dict
        Must contain at least ``date``, ``amount``, ``transaction_type``.

    Returns
    -------
    dict  – the structured transaction, ready for API response / DB insert.
    """
    txn_type = _coerce_type(raw.get("transaction_type", "debit"))
    amount = round(abs(float(raw.get("amount", 0))), 2)
    txn_date = _coerce_date(raw.get("date"))

    original_hash = raw.get("original_hash", "")
    txn_id = str(uuid.uuid5(_TXN_NAMESPACE, original_hash)) if original_hash else str(uuid.uuid4())

    merchant = raw.get("merchant_clean") or raw.get("description_clean") or "Unknown"
    desc_clean = raw.get("description_clean") or merchant
    desc_masked = raw.get("description_masked") or desc_clean

    return {
        "id": txn_id,
        "date": txn_date.isoformat() if isinstance(txn_date, date) else str(txn_date),
        "amount": amount,
        "transaction_type": txn_type,
        "category": raw.get("category", "Uncategorized"),
        "merchant_clean": merchant,
        "description_clean": desc_clean,
        "description_masked": desc_masked,
        "original_hash": original_hash,
        "time_hour": _coerce_time_hour(raw.get("time_hour")),
        "is_recurring": bool(raw.get("is_recurring", False)),
        "metadata": {
            "raw_description": raw.get("raw_description", ""),
        },
    }


def structure_batch(transactions: list[dict]) -> list[dict]:
    """Structure a list of transaction dicts.

    Invalid rows are logged and skipped (never raises).
    """
    structured: list[dict] = []
    for i, raw in enumerate(transactions):
        try:
            structured.append(structure_transaction(raw))
        except Exception as exc:
            logger.warning("Skipping transaction %d during structuring: %s", i, exc)
    logger.info(
        "Structured %d / %d transactions", len(structured), len(transactions)
    )
    return structured


# ── Private helpers ─────────────────────────────────────────────────


def _coerce_type(raw_type: Any) -> str:
    """Normalize transaction type to ``'credit'`` or ``'debit'``."""
    t = str(raw_type).strip().lower()
    if t in _VALID_TYPES:
        return t
    if t in ("cr", "c", "deposit"):
        return "credit"
    return "debit"


def _coerce_date(value: Any) -> Optional[date]:
    """Return a ``datetime.date`` or the original value (string fallback)."""
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime as dt
        return dt.fromisoformat(str(value)).date()
    except Exception:
        return value  # let the caller stringify it


def _coerce_time_hour(value: Any) -> Optional[int]:
    """Return an int 0-23 or None."""
    if value is None:
        return None
    try:
        h = int(value)
        return h if 0 <= h <= 23 else None
    except (ValueError, TypeError):
        return None
