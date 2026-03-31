"""CSV Parser — handles messy real-world bank statement formats.

Supports:
- Multiple date formats
- Split debit/credit columns or single amount column
- Auto-detection of column names using aliases
- Header row detection (skips metadata rows)
- Encoding detection
"""
import csv
import io
import re
import logging
from datetime import datetime, date
from typing import Optional

import pandas as pd

from server.utils.security import sanitize_csv_value, mask_account_number, hash_row
from server.utils.constants import DATE_FORMATS, COLUMN_ALIASES

logger = logging.getLogger(__name__)


class CSVParser:
    """Parse and normalize bank statement CSV files."""

    def __init__(self):
        self.detected_columns: dict[str, str] = {}
        self.date_format: Optional[str] = None

    def parse(self, file_content: bytes, filename: str = "") -> list[dict]:
        """Main entry point: parse CSV bytes into normalized transaction dicts.
        
        Returns list of dicts with keys:
            date, time_hour, description, amount, transaction_type,
            original_hash, raw_description
        """
        # Decode with fallback encodings
        text = self._decode(file_content)
        
        # Sanitize all values
        text = self._sanitize_text(text)
        
        # Find the header row (skip bank metadata)
        header_row_idx, lines = self._find_header_row(text)
        if header_row_idx is None:
            raise ValueError("Could not detect a valid header row in the CSV file.")

        # Parse into DataFrame
        csv_text = "\n".join(lines[header_row_idx:])
        df = pd.read_csv(io.StringIO(csv_text), skipinitialspace=True)
        
        # Clean column names
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Map columns to standard names
        self._detect_columns(df)
        
        # Parse transactions
        transactions = []
        for idx, row in df.iterrows():
            try:
                txn = self._parse_row(row, idx)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                logger.warning(f"Skipping row {idx}: {e}")
                continue

        logger.info(f"Parsed {len(transactions)} transactions from {filename}")
        return transactions

    def _decode(self, content: bytes) -> str:
        """Try multiple encodings to decode the CSV content."""
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, AttributeError):
                continue
        raise ValueError("Could not decode CSV file with any supported encoding.")

    def _sanitize_text(self, text: str) -> str:
        """Remove null bytes and sanitize the raw text."""
        text = text.replace("\x00", "")
        return text

    def _find_header_row(self, text: str) -> tuple[Optional[int], list[str]]:
        """Detect the header row by looking for known column aliases.
        
        Bank CSVs often have metadata rows before the actual data header.
        """
        lines = text.strip().split("\n")
        all_aliases = set()
        for aliases in COLUMN_ALIASES.values():
            all_aliases.update(a.lower() for a in aliases)

        for i, line in enumerate(lines[:20]):  # Check first 20 lines
            cells = [c.strip().strip('"').lower() for c in line.split(",")]
            matches = sum(1 for c in cells if c in all_aliases)
            if matches >= 2:  # At least date + one other column
                return i, lines
        
        # Fallback: try first row
        return 0, lines

    def _detect_columns(self, df: pd.DataFrame):
        """Map DataFrame columns to standard names using aliases."""
        columns = list(df.columns)
        self.detected_columns = {}

        for standard_name, aliases in COLUMN_ALIASES.items():
            for col in columns:
                col_clean = col.strip().lower()
                if col_clean in [a.lower() for a in aliases]:
                    self.detected_columns[standard_name] = col
                    break

        required = ["date"]
        has_amount = "amount" in self.detected_columns
        has_debit_credit = "debit" in self.detected_columns or "credit" in self.detected_columns
        
        if not has_amount and not has_debit_credit:
            raise ValueError(
                f"Could not find amount column. Detected columns: {columns}"
            )

        for req in required:
            if req not in self.detected_columns:
                raise ValueError(
                    f"Could not find '{req}' column. Detected columns: {columns}"
                )

    def _parse_row(self, row: pd.Series, idx: int) -> Optional[dict]:
        """Parse a single CSV row into a normalized transaction dict."""
        # Parse date
        date_val = self._parse_date(row.get(self.detected_columns.get("date", ""), ""))
        if date_val is None:
            return None

        # Parse description
        desc_col = self.detected_columns.get("description", "")
        raw_description = str(row.get(desc_col, "")).strip() if desc_col else ""
        if not raw_description or raw_description.lower() == "nan":
            raw_description = "No description"

        # Parse amount and determine type
        amount, txn_type = self._parse_amount(row)
        if amount is None or amount == 0:
            return None

        # Extract time hour if available (from description or time column)
        time_hour = self._extract_time_hour(raw_description)

        # Mask sensitive data
        masked_description = mask_account_number(raw_description)

        # Generate dedup hash from original row data
        row_str = ",".join(str(v) for v in row.values)
        original_hash = hash_row(row_str)

        return {
            "date": date_val,
            "time_hour": time_hour,
            "description": sanitize_csv_value(masked_description),
            "raw_description": raw_description,
            "amount": abs(amount),
            "transaction_type": txn_type,
            "original_hash": original_hash,
        }

    def _parse_date(self, value) -> Optional[date]:
        """Parse date from various formats."""
        if pd.isna(value):
            return None
        
        date_str = str(value).strip()
        if not date_str:
            return None

        # Try cached format first
        if self.date_format:
            try:
                return datetime.strptime(date_str, self.date_format).date()
            except (ValueError, TypeError):
                pass

        # Try all known formats
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(date_str, fmt).date()
                self.date_format = fmt  # Cache for subsequent rows
                return parsed
            except (ValueError, TypeError):
                continue

        # Try pandas as last resort
        try:
            return pd.to_datetime(date_str, dayfirst=True).date()
        except Exception:
            return None

    def _parse_amount(self, row: pd.Series) -> tuple[Optional[float], str]:
        """Parse amount and determine if debit or credit.
        
        Handles:
        - Single 'amount' column with type indicator
        - Separate 'debit' and 'credit' columns
        - Amount with CR/DR suffix
        - Negative amounts as debits
        """
        # Try separate debit/credit columns first
        debit_col = self.detected_columns.get("debit", "")
        credit_col = self.detected_columns.get("credit", "")

        if debit_col or credit_col:
            debit = self._clean_amount(row.get(debit_col, 0)) if debit_col else 0
            credit = self._clean_amount(row.get(credit_col, 0)) if credit_col else 0

            if debit and debit > 0:
                return debit, "debit"
            elif credit and credit > 0:
                return credit, "credit"
            return None, ""

        # Single amount column
        amount_col = self.detected_columns.get("amount", "")
        if amount_col:
            raw_amount = row.get(amount_col, 0)
            amount = self._clean_amount(raw_amount)
            
            if amount is None:
                return None, ""

            # Check type column
            type_col = self.detected_columns.get("type", "")
            if type_col:
                txn_type = str(row.get(type_col, "")).strip().lower()
                if txn_type in ("dr", "debit", "d"):
                    return abs(amount), "debit"
                elif txn_type in ("cr", "credit", "c"):
                    return abs(amount), "credit"

            # Negative = debit, positive = credit
            if amount < 0:
                return abs(amount), "debit"
            return abs(amount), "credit"

        return None, ""

    def _clean_amount(self, value) -> Optional[float]:
        """Clean amount string to float."""
        if pd.isna(value):
            return 0
        
        amount_str = str(value).strip()
        if not amount_str or amount_str.lower() == "nan":
            return 0

        # Remove currency symbols, commas, spaces
        amount_str = re.sub(r'[₹$€£,\s]', '', amount_str)
        # Remove DR/CR suffixes
        amount_str = re.sub(r'(?i)\s*(dr|cr|debit|credit)\.?\s*$', '', amount_str)
        
        try:
            return float(amount_str)
        except ValueError:
            return None

    def _extract_time_hour(self, description: str) -> Optional[int]:
        """Try to extract transaction time from description."""
        # Pattern: HH:MM or HH:MM:SS
        time_match = re.search(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b', description)
        if time_match:
            hour = int(time_match.group(1))
            if 0 <= hour <= 23:
                return hour
        return None
