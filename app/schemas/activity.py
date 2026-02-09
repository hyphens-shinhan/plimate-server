from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.post import EventStatus


class ActivityStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"


class CouncilReportStatus(BaseModel):
    title: str | None = None
    exists: bool
    is_submitted: bool


class AcademicReportStatus(BaseModel):
    status: ActivityStatus


class MandatoryActivityStatus(BaseModel):
    id: UUID
    title: str
    activity_type: str
    status: ActivityStatus
    due_date: date


class AppliedEventStatus(BaseModel):
    id: UUID
    title: str
    event_date: datetime
    status: EventStatus


class MonthlyActivityStatus(BaseModel):
    month: int
    council_report: CouncilReportStatus
    academic_report: AcademicReportStatus


class YearlyActivitySummary(BaseModel):
    year: int
    council_id: UUID | None = None
    months: list[MonthlyActivityStatus]
    council_all_completed: bool
    academic_all_completed: bool
    academic_is_monitored: bool
    mandatory_activities: list[MandatoryActivityStatus]
    applied_events: list[AppliedEventStatus]


class ActivitiesSummaryResponse(BaseModel):
    min_year: int
    max_year: int
    years: list[YearlyActivitySummary]
