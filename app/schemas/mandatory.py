from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.academic import AcademicGoalCategory


class MandatoryActivityType(str, Enum):
    GOAL = "GOAL"
    SIMPLE_REPORT = "SIMPLE_REPORT"
    URL_REDIRECT = "URL_REDIRECT"


# --- Admin: Activity Management ---
class MandatoryActivityCreate(BaseModel):
    title: str
    year: int
    due_date: date
    activity_type: MandatoryActivityType
    external_url: str | None = None  # Required for URL_REDIRECT


class MandatoryActivityResponse(BaseModel):
    id: UUID
    title: str
    year: int
    due_date: date
    activity_type: MandatoryActivityType
    external_url: str | None
    created_at: datetime


# --- GOAL type ---
class MandatoryGoalCreate(BaseModel):
    category: AcademicGoalCategory
    custom_category: str | None = None
    content: str = Field(..., min_length=1)
    plan: str = Field(..., min_length=1)
    outcome: str = Field(..., min_length=1)


class MandatoryGoalResponse(BaseModel):
    id: UUID
    category: AcademicGoalCategory
    custom_category: str | None = None
    content: str
    plan: str
    outcome: str


# --- Submission schemas by type ---
class GoalSubmissionCreate(BaseModel):
    goals: list[MandatoryGoalCreate] = Field(..., min_length=2)


class GoalSubmissionUpdate(BaseModel):
    goals: list[MandatoryGoalCreate] = Field(..., min_length=2)


class SimpleReportSubmissionCreate(BaseModel):
    report_title: str
    report_content: str
    activity_date: date
    location: str
    image_urls: list[str] | None = None


class SimpleReportSubmissionUpdate(BaseModel):
    report_title: str
    report_content: str
    activity_date: date
    location: str
    image_urls: list[str] | None = None


# --- Unified Response ---
class MandatorySubmissionResponse(BaseModel):
    id: UUID
    activity_id: UUID
    activity: MandatoryActivityResponse
    user_id: UUID
    is_submitted: bool
    created_at: datetime
    submitted_at: datetime | None
    # GOAL type fields
    goals: list[MandatoryGoalResponse] | None = None
    # SIMPLE_REPORT type fields
    report_title: str | None = None
    report_content: str | None = None
    activity_date: date | None = None
    location: str | None = None
    image_urls: list[str] | None = None


class MandatorySubmissionLookupResponse(BaseModel):
    activity: MandatoryActivityResponse | None
    submission: MandatorySubmissionResponse | None


class MandatoryActivitiesForYearResponse(BaseModel):
    year: int
    activities: list[MandatorySubmissionLookupResponse]
