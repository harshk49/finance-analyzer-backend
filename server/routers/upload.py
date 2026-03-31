"""Upload router — handles CSV file upload and processing.

Pipeline: Upload → Parse → **Clean** → Merchant Clean → Categorize → **Structure** → Return
"""
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException

from server.config import MAX_UPLOAD_SIZE_MB
from server.utils.security import generate_session_token, sanitize_filename
from server.services.csv_parser import CSVParser
from server.services.data_cleaner import DataCleaner
from server.services.merchant_cleaner import MerchantCleaner
from server.services.categorizer import TransactionCategorizer
from server.services.transaction_structurer import structure_batch
from server.schemas.upload import UploadResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload", tags=["Upload"])

# In-memory session storage (replace with DB in production)
# Key: session_token → Value: processed transaction list
sessions: dict[str, list[dict]] = {}


@router.post("/csv", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    """Upload and process a bank statement CSV file.

    Returns a session token to use for all subsequent analytics queries.
    The raw file is NOT stored — only cleaned, masked data is kept.
    """
    # ── Validate file ───────────────────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    content = await file.read()

    if len(content) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_MB}MB.",
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    try:
        safe_name = sanitize_filename(file.filename)

        # ── Step 1: Parse CSV → raw transaction dicts ───────────────
        parser = CSVParser()
        raw_transactions = parser.parse(content, safe_name)
        if not raw_transactions:
            raise HTTPException(
                status_code=400,
                detail="No valid transactions found in the file. Check the format.",
            )

        # ── Step 2: Data cleaning (normalize, dedup, fill blanks) ───
        cleaner = DataCleaner()
        cleaned = cleaner.clean(raw_transactions)

        # ── Step 3: Merchant name cleaning ──────────────────────────
        merchant_cleaner = MerchantCleaner()
        cleaned = merchant_cleaner.clean_batch(cleaned)

        # ── Step 4: Categorize ──────────────────────────────────────
        categorizer = TransactionCategorizer()
        cleaned = categorizer.categorize_batch(cleaned)

        # ── Step 5: Structure into standard JSON ────────────────────
        transactions = structure_batch(cleaned)

        if not transactions:
            raise HTTPException(
                status_code=400,
                detail="All transactions were filtered during cleaning. Check the file.",
            )

        # ── Generate session ────────────────────────────────────────
        session_token = generate_session_token()
        sessions[session_token] = transactions

        # Date range
        dates = [t["date"] for t in transactions]
        date_range = {
            "start": str(min(dates)),
            "end": str(max(dates)),
        }

        categorized_count = sum(
            1 for t in transactions if t.get("category") != "Uncategorized"
        )

        logger.info(
            "Processed %d → %d transactions (%d categorized) for session %s...",
            len(raw_transactions),
            len(transactions),
            categorized_count,
            session_token[:8],
        )

        return UploadResponse(
            session_token=session_token,
            transactions_parsed=len(transactions),
            transactions_categorized=categorized_count,
            date_range=date_range,
            message=f"Successfully processed {len(transactions)} transactions.",
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing CSV upload")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


def get_session_transactions(session_token: str) -> list[dict]:
    """Helper to retrieve transactions for a session. Used by other routers."""
    if session_token not in sessions:
        raise HTTPException(
            status_code=404, detail="Session not found. Please upload a CSV first."
        )
    return sessions[session_token]
