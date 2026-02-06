from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.post import PostAuthor


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
    activity_date: date
    location: str
    content: str | None = None
    image_urls: list[str] | None = None
    receipts: list[ReceiptCreate] | None = None
    attendance: list[AttendanceItem] | None = None


class ReportUpdate(BaseModel):
    title: str | None = None
    activity_date: date | None = None
    location: str | None = None
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
    name: str
    avatar_url: str | None = None
    status: AttendanceStatus
    confirmation: ConfirmationStatus
    is_leader: bool = False


class ReportResponse(BaseModel):
    id: UUID
    council_id: UUID
    year: int
    month: int
    title: str
    activity_date: date | None
    location: str | None
    is_submitted: bool
    is_public: bool
    submitted_at: datetime
    receipts: list[ReceiptResponse]
    attendance: list[AttendanceResponse]
    content: str | None
    image_urls: list[str] | None


class PublicAttendanceResponse(BaseModel):
    """Attendance info for public feed - excludes confirmation status."""
    name: str


class PublicReportResponse(BaseModel):
    """Report info for public feed - excludes receipts, includes council info."""
    id: UUID  # This is the post_id - primary identifier for all interactions
    report_id: UUID  # Original activity report ID for admin operations
    title: str
    activity_date: date | None
    location: str | None
    content: str | None
    image_urls: list[str] | None
    attendance: list[PublicAttendanceResponse]
    submitted_at: datetime
    author: PostAuthor | None = None
    like_count: int = 0
    comment_count: int = 0
    scrap_count: int = 0
    is_liked: bool = False
    is_scrapped: bool = False
