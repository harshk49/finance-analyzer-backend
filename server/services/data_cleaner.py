"""Data Cleaner — normalizes, deduplicates, and validates raw parsed transactions.

Sits between CSVParser (raw rows) and MerchantCleaner (semantic cleaning).
Responsible for:
  • Date format normalization  → yyyy-mm-dd (ISO)
  • Amount sign standardization → always positive, type carries semantics
  • Duplicate detection         → SHA-256 hash + fuzzy (date+amount+desc)
  • Missing merchant handling   → inference from UPI/NEFT metadata
"""
import hashlib
import logging
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Optional

import pandas as pd

from server.utils.constants import DATE_FORMATS

logger = logging.getLogger(__name__)


class DataCleaner:
    """Clean and normalize a list of parsed transaction dicts."""

    # ── Public API ──────────────────────────────────────────────────

    def clean(self, transactions: list[dict]) -> list[dict]:
        """Full cleaning pipeline. Returns a new list (does NOT mutate input)."""

        cleaned = [self._normalize_row(txn) for txn in transactions]

        # Drop rows that failed normalization
        cleaned = [t for t in cleaned if t is not None]

        # Deduplicate
        cleaned = self._deduplicate(cleaned)

        # Fill missing merchants
        cleaned = [self._fill_missing_merchant(t) for t in cleaned]

        logger.info(
            "DataCleaner: %d → %d transactions after cleaning",
            len(transactions),
            len(cleaned),
        )
        return cleaned

    # ── Row-level normalization ─────────────────────────────────────

    def _normalize_row(self, txn: dict) -> Optional[dict]:
        """Normalize a single transaction dict. Returns None on failure."""
        out = dict(txn)  # shallow copy

        # ── Date normalization ──────────────────────────────────────
        out["date"] = self._normalize_date(txn.get("date"))
        if out["date"] is None:
            logger.debug("Dropping row — unparseable date: %s", txn.get("date"))
            return None

        # ── Amount standardization ──────────────────────────────────
        amount, txn_type = self._normalize_amount(
            txn.get("amount"), txn.get("transaction_type", "")
        )
        if amount is None or amount == 0:
            logger.debug("Dropping row — zero/missing amount")
            return None
        out["amount"] = amount
        out["transaction_type"] = txn_type

        # ── Description normalization ───────────────────────────────
        desc = str(txn.get("description", "") or txn.get("raw_description", "")).strip()
        if not desc or desc.lower() == "nan":
            desc = ""
        out["description"] = desc
        out["raw_description"] = str(txn.get("raw_description", desc)).strip()

        # Ensure hash exists
        if not out.get("original_hash"):
            row_str = f"{out['date']}|{out['amount']}|{out['description']}"
            out["original_hash"] = hashlib.sha256(
                row_str.encode("utf-8")
            ).hexdigest()

        return out

    # ── Date helpers ────────────────────────────────────────────────

    def _normalize_date(self, value) -> Optional[date]:
        """Convert any date representation into a ``datetime.date``."""
        if value is None:
            return None

        # Already a date/datetime object
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

        date_str = str(value).strip()
        if not date_str or date_str.lower() == "nan":
            return None

        # Try all known format strings
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue

        # Pandas as last resort (handles many edge cases)
        try:
            return pd.to_datetime(date_str, dayfirst=True).date()
        except Exception:
            return None

    # ── Amount helpers ──────────────────────────────────────────────

    def _normalize_amount(
        self, raw_amount, raw_type: str
    ) -> tuple[Optional[float], str]:
        """Ensure amount is always a positive float; type carries debit/credit.

        Rules:
        • Negative value → debit (even if raw_type says credit — sign wins)
        • Positive value with raw_type == "" → default to "debit"
        • Strips currency symbols, commas, whitespace, DR/CR suffixes
        """
        if raw_amount is None:
            return None, ""

        if isinstance(raw_amount, (int, float)):
            amount = float(raw_amount)
        else:
            amount = self._parse_amount_string(str(raw_amount))
            if amount is None:
                return None, ""

        # Determine type from sign if not explicitly provided
        txn_type = raw_type.lower().strip() if raw_type else ""

        if amount < 0:
            txn_type = "debit"
        elif not txn_type:
            txn_type = "debit"  # conservative default

        # Normalize valid synonyms
        if txn_type in ("dr", "d", "withdrawal"):
            txn_type = "debit"
        elif txn_type in ("cr", "c", "deposit"):
            txn_type = "credit"

        return round(abs(amount), 2), txn_type

    def _parse_amount_string(self, s: str) -> Optional[float]:
        """Parse a messy amount string into a float."""
        s = s.strip()
        if not s or s.lower() == "nan":
            return None

        # Strip currency symbols, commas, spaces
        s = re.sub(r"[₹$€£,\s]", "", s)
        # Strip trailing DR / CR markers
        s = re.sub(r"(?i)\s*(dr|cr|debit|credit)\.?\s*$", "", s)
        # Handle parenthesized negatives: (1234.56) → -1234.56
        paren_match = re.match(r"^\(([\d.]+)\)$", s)
        if paren_match:
            s = f"-{paren_match.group(1)}"

        try:
            return float(s)
        except ValueError:
            return None

    # ── Deduplication ───────────────────────────────────────────────

    def _deduplicate(self, transactions: list[dict]) -> list[dict]:
        """Remove exact duplicates (by hash) and near-duplicates.

        Near-duplicate:  same date + same amount + similar description,
        which can happen when a bank CSV double-exports rows or re-states
        pending→posted transactions.
        """
        seen_hashes: set[str] = set()
        # key: (date_str, amount) → list of descriptions already kept
        fuzzy_index: dict[tuple[str, float], list[str]] = defaultdict(list)
        unique: list[dict] = []

        for txn in transactions:
            # ── Exact duplicate ─────────────────────────────────────
            h = txn.get("original_hash", "")
            if h and h in seen_hashes:
                continue
            if h:
                seen_hashes.add(h)

            # ── Fuzzy duplicate ─────────────────────────────────────
            key = (str(txn["date"]), txn["amount"])
            desc = txn.get("description", "")
            if self._is_fuzzy_dup(key, desc, fuzzy_index):
                continue

            fuzzy_index[key].append(desc)
            unique.append(txn)

        removed = len(transactions) - len(unique)
        if removed:
            logger.info("Removed %d duplicate transactions", removed)
        return unique

    @staticmethod
    def _is_fuzzy_dup(
        key: tuple[str, float],
        desc: str,
        index: dict[tuple[str, float], list[str]],
    ) -> bool:
        """Check if desc is a near-duplicate of any already-seen description
        for the same (date, amount) pair."""
        if key not in index:
            return False
        # Simple character-level similarity (avoids heavy rapidfuzz import)
        desc_set = set(desc.lower().split())
        for existing in index[key]:
            existing_set = set(existing.lower().split())
            if not desc_set or not existing_set:
                if desc.strip() == existing.strip():
                    return True
                continue
            overlap = len(desc_set & existing_set) / max(
                len(desc_set | existing_set), 1
            )
            if overlap > 0.8:
                return True
        return False

    # ── Missing-merchant inference ──────────────────────────────────

    _UPI_PAYEE_RE = re.compile(
        r"(?i)"
        r"(?:upi[-/\s]*)?"               # optional UPI prefix
        r"(?:"
        r"(?:paid\s+to|sent\s+to|p2m|cr)\s+"  # transfer verb
        r")?"
        r"([A-Za-z][A-Za-z0-9 _.]{1,40})"    # capture merchant/payee
    )

    _TRANSFER_KEYWORDS = re.compile(
        r"(?i)\b(?:neft|rtgs|imps|ib\s*fund|mb\s*fund|fund\s*transfer|self\s*transfer)\b"
    )

    def _fill_missing_merchant(self, txn: dict) -> dict:
        """If description is empty/generic, try to infer a useful label."""
        desc = txn.get("description", "")
        raw = txn.get("raw_description", desc)

        if desc and desc.lower() not in ("", "no description", "unknown", "nan"):
            return txn  # already has a meaningful description

        # Try extracting payee from raw description
        m = self._UPI_PAYEE_RE.search(raw)
        if m:
            txn["description"] = m.group(1).strip()
            return txn

        # Label if it looks like a self-transfer
        if self._TRANSFER_KEYWORDS.search(raw):
            txn["description"] = "Fund Transfer"
            return txn

        # Last resort — use a sanitized snippet of raw_description
        snippet = re.sub(r"\d{6,}", "", raw)  # strip long numbers
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if snippet and len(snippet) > 2:
            txn["description"] = snippet[:60]
        else:
            txn["description"] = "Unknown Transaction"

        return txn
