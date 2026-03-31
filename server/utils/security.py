"""Security utilities — data masking, sanitization, session management."""
import hashlib
import re
import secrets
from typing import Optional


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


def hash_row(row_data: str) -> str:
    """SHA-256 hash of a raw CSV row for deduplication."""
    return hashlib.sha256(row_data.encode("utf-8")).hexdigest()


def mask_account_number(text: str) -> str:
    """Mask account numbers, card numbers, and sensitive IDs in text.
    
    Replaces sequences of 4+ digits (possibly separated by dashes/spaces)
    with masked versions showing only last 4 characters.
    """
    # Mask card numbers (16 digits with optional separators)
    text = re.sub(
        r'\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?)(\d{4})\b',
        r'XXXX-XXXX-XXXX-\2',
        text
    )
    # Mask account numbers (8+ digit sequences)
    text = re.sub(
        r'\b(\d{4,})(\d{4})\b',
        lambda m: 'X' * len(m.group(1)) + m.group(2),
        text
    )
    # Mask UPI IDs (name@bankname)
    text = re.sub(
        r'([a-zA-Z0-9._]+)@([a-zA-Z]+)',
        lambda m: m.group(1)[:2] + '***@' + m.group(2),
        text
    )
    return text


def sanitize_csv_value(value: str) -> str:
    """Prevent CSV formula injection attacks.
    
    Strips leading characters that could trigger formula execution
    in spreadsheet applications: =, +, -, @, |, \\
    """
    if not isinstance(value, str):
        return str(value)
    
    dangerous_chars = ('=', '+', '-', '@', '|', '\\', '\t', '\r', '\n')
    cleaned = value.strip()
    
    # Remove leading dangerous characters but preserve negative numbers
    while cleaned and cleaned[0] in dangerous_chars:
        if cleaned[0] == '-' and len(cleaned) > 1 and cleaned[1].isdigit():
            break  # Preserve negative numbers
        cleaned = cleaned[1:].strip()
    
    return cleaned


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent path traversal."""
    # Remove path separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\x00', '')
    # Keep only safe characters
    filename = re.sub(r'[^\w\s\-.]', '_', filename)
    return filename[:255]  # Limit length
