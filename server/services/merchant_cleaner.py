"""Merchant name cleaner — normalizes noisy transaction descriptions.

Handles the *real-world mess* found in Indian bank statements:
  • UPI strings:  ``UPI-SWIGGY-Q1234567890-YESB0001234-IOBKXXXXXXXX``
  • NEFT/RTGS:    ``NEFT/CR/0423698712/JOHN DOE/HDFC0001234``
  • POS:          ``POS 422113XXXXXX2345 BIG BAZAAR PVT 28/03``
  • IMPS:         ``IMPS/P2M/402712345678/AMAZON SELLER/UTIB``
  • Generic:      ``IB FUND TRANSFER-MMT/IMPS/123456789012/…``

Pipeline:
  1. Remove UPI/payment noise (regex layer)
  2. Remove bank-specific noise (ref nos, IFSC, dates, a/c numbers)
  3. Match against known-merchant keyword dictionary
  4. Fuzzy-match fallback via RapidFuzz
  5. Extract first meaningful segment
  6. Title-case and truncate
"""
import re
from typing import Optional

from rapidfuzz import fuzz, process

from server.utils.constants import UPI_PATTERNS, MERCHANT_KEYWORDS


class MerchantCleaner:
    """Clean and normalize merchant names from transaction descriptions."""

    # ── Known-merchant map (noisy key → display name) ───────────────
    # Built from MERCHANT_KEYWORDS in constants.py for O(1) substring lookups
    KNOWN_MERCHANTS: dict[str, str] = MERCHANT_KEYWORDS

    # ── Core UPI regex patterns ─────────────────────────────────────
    # These target the *structure* of UPI transaction strings so they
    # work regardless of which bank issued the statement.
    _UPI_STRUCTURAL_PATTERNS: list[tuple[re.Pattern, str]] = [
        # Full UPI string:  UPI-<MERCHANT>-<RefID>-<RemitterIFSC>-<BeneficiaryAcc>
        (re.compile(
            r"(?i)^UPI[-/]"
            r"([A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)"   # group 1 = merchant
            r"[-/][A-Za-z0-9]{8,}",                   # ref / IFSC / acc tail
        ), r"\1"),

        # IMPS P2M / P2P:  IMPS/P2M/<ref>/<MERCHANT>/<IFSC-prefix>
        (re.compile(
            r"(?i)IMPS\s*/\s*(?:P2[MP])\s*/\s*\d{6,}\s*/\s*"
            r"([A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)"   # merchant
            r"\s*/",
        ), r"\1"),

        # NEFT/RTGS:  NEFT/CR/<ref>/<NAME>/<IFSC>
        (re.compile(
            r"(?i)(?:NEFT|RTGS)\s*/\s*(?:CR|DR)\s*/\s*\w{6,}\s*/\s*"
            r"([A-Za-z][A-Za-z0-9 .&'\-]{1,40}?)"
            r"\s*/",
        ), r"\1"),
    ]

    # ── Noise patterns (order matters — run top-to-bottom) ──────────
    _NOISE_PATTERNS: list[re.Pattern] = [
        # UPI handles:  name@okaxis, name@ybl
        re.compile(r"[a-zA-Z0-9._]+@[a-zA-Z]{2,10}"),
        # Transaction / Reference IDs
        re.compile(r"(?i)(?:transaction|txn|ref|utr)\s*(?:id|no|number|#)?\s*:?\s*[\w]{6,}"),
        # IFSC codes:  HDFC0001234
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        # Account / Card numbers
        re.compile(r"(?i)(?:a/c|ac|acct|card)\s*(?:no)?\s*:?\s*[\dxX*]{4,}"),
        # Long digit strings (>= 6 digits)
        re.compile(r"\b\d{6,}\b"),
        # Dates embedded in descriptions
        re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
        # Content in parentheses / brackets
        re.compile(r"[\(\[].*?[\)\]]"),
        # Common transfer verbs that aren't merchant names
        re.compile(r"(?i)\b(?:ib|mb|net)\s*(?:fund)?\s*transfer\b"),
        re.compile(r"(?i)\b(?:bill)\s*pay(?:ment)?\b"),
    ]

    # ── Payment-mode prefixes to strip ──────────────────────────────
    _PREFIX_RE = re.compile(
        r"(?i)^(?:UPI|NEFT|RTGS|IMPS|POS|ECOM|INB|MOB|ATM|CMS|ECS|SI)\s*[-/\s]*"
    )

    # ────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────

    def clean(self, description: str) -> str:
        """Clean a transaction description into a merchant name."""
        if not description:
            return "Unknown"

        cleaned = description.strip()

        # Step 1: Try to extract merchant from structured UPI/IMPS/NEFT string
        extracted = self._extract_from_structure(cleaned)
        if extracted:
            cleaned = extracted

        # Step 2: Remove remaining UPI noise (constants.py patterns)
        cleaned = self._remove_upi_noise(cleaned)

        # Step 3: Strip payment-mode prefix
        cleaned = self._PREFIX_RE.sub("", cleaned).strip()

        # Step 4: Remove bank-specific noise (refs, IFSC, a/c nos)
        cleaned = self._remove_bank_noise(cleaned)

        # Step 5: Try to match known merchants (keyword dict)
        known = self._match_known_merchant(cleaned)
        if known:
            return known

        # Step 6: Extract best remaining text segment
        cleaned = self._extract_merchant_name(cleaned)

        # Step 7: Final title-case + truncate
        cleaned = self._final_cleanup(cleaned)

        return cleaned if cleaned else "Unknown"

    def clean_batch(self, transactions: list[dict]) -> list[dict]:
        """Add ``merchant_clean`` and ``description_clean`` to each txn dict."""
        for txn in transactions:
            desc = txn.get("description", "") or txn.get("raw_description", "")
            merchant = self.clean(desc)
            txn["merchant_clean"] = merchant
            txn["description_clean"] = merchant
            txn["description_masked"] = txn.get("description", merchant)
        return transactions

    # ────────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────────

    def _extract_from_structure(self, text: str) -> Optional[str]:
        """Attempt to pluck merchant name from a known UPI/IMPS/NEFT format."""
        for pattern, repl in self._UPI_STRUCTURAL_PATTERNS:
            m = pattern.search(text)
            if m:
                name = m.expand(repl).strip()
                # Sanity: must look like a name (>1 alpha char)
                if re.search(r"[A-Za-z]{2,}", name):
                    return name
        return None

    def _remove_upi_noise(self, text: str) -> str:
        """Remove UPI transaction noise patterns from constants.py."""
        for pattern, replacement in UPI_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text.strip()

    def _remove_bank_noise(self, text: str) -> str:
        """Strip reference numbers, IFSC codes, account numbers, etc."""
        for pattern in self._NOISE_PATTERNS:
            text = pattern.sub(" ", text)
        return text.strip()

    def _match_known_merchant(self, text: str) -> Optional[str]:
        """Match against known merchant names — keyword then fuzzy."""
        text_lower = text.lower()

        # ── Direct substring match (fast path) ─────────────────────
        for key, clean_name in self.KNOWN_MERCHANTS.items():
            if key in text_lower:
                return clean_name

        # ── Fuzzy match per word (RapidFuzz, score_cutoff=80) ──────
        words = text_lower.split()
        for word in words:
            if len(word) < 3:
                continue
            match = process.extractOne(
                word,
                self.KNOWN_MERCHANTS.keys(),
                scorer=fuzz.ratio,
                score_cutoff=80,
            )
            if match:
                return self.KNOWN_MERCHANTS[match[0]]

        return None

    @staticmethod
    def _extract_merchant_name(text: str) -> str:
        """Take the first meaningful text segment (split by / - | \\)."""
        text = re.sub(r"\s+", " ", text).strip()
        segments = re.split(r"[-/|\\]", text)
        for segment in segments:
            segment = segment.strip()
            if len(segment) < 2 or segment.replace(" ", "").isdigit():
                continue
            return segment
        return text

    @staticmethod
    def _final_cleanup(text: str) -> str:
        """Title-case, collapse whitespace, and truncate."""
        text = re.sub(r"^[\s\-/]+|[\s\-/]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        if text.isupper() or text.islower():
            text = text.title()
        if len(text) > 50:
            text = text[:50].rsplit(" ", 1)[0]
        return text
