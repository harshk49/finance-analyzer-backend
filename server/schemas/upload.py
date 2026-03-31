"""Upload response schemas."""
from pydantic import BaseModel


class UploadResponse(BaseModel):
    session_token: str
    transactions_parsed: int
    transactions_categorized: int
    date_range: dict  # {start: str, end: str}
    message: str
