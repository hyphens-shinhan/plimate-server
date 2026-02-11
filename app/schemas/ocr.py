from pydantic import BaseModel


class ReceiptOcrItem(BaseModel):
    """Single item extracted from receipt OCR (name + price)."""

    name: str
    price: int


class ReceiptOcrResponse(BaseModel):
    """Response of receipt OCR: list of extracted items."""

    items: list[ReceiptOcrItem]
