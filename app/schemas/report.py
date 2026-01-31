from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


class ConfirmationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


class ReceiptItemCreate(BaseModel):
    item_name: str
    price: int


class ReceiptCreate(BaseModel):
    store_name: str
    image_url: str
    items: list[ReceiptItemCreate]


class AttendanceItem(BaseModel):
    user_id: UUID
    status: AttendanceStatus


class ReportCreate(BaseModel):
    title: str
    content: str | None = None
    image_urls: list[str] | None = None
    receipts: list[ReceiptCreate] | None = None
    attendance: list[AttendanceItem] | None = None


class ReceiptItemResponse(BaseModel):
    id: UUID
    item_name: str
    price: int


class ReceiptResponse(BaseModel):
    id: UUID
    store_name: str
    image_url: str
    created_at: datetime
    items: list[ReceiptItemResponse]


class AttendanceResponse(BaseModel):
    user_id: UUID
    status: AttendanceStatus
    confirmation: ConfirmationStatus


class ReportResponse(BaseModel):
    id: UUID
    council_id: UUID
    month: int
    title: str
    submitted_at: datetime
    receipts: list[ReceiptResponse]
    attendance: list[AttendanceResponse]
    content: str | None
    image_urls: list[str] | None
