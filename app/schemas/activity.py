from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.post import EventStatus


class CouncilReportStatus(BaseModel):
    title: str | None = None
    is_completed: bool


class AcademicReportStatus(BaseModel):
    is_completed: bool


class MandatoryActivityStatus(BaseModel):
    id: UUID
    title: str
    activity_type: str  # GOAL, SIMPLE_REPORT, URL_REDIRECT
    is_submitted: bool
    due_date: date


class MandatoryReportStatus(BaseModel):
    activities: list[MandatoryActivityStatus]


class AppliedEventStatus(BaseModel):
    id: UUID
    title: str
    event_date: datetime
    status: EventStatus


class AppliedEventsStatus(BaseModel):
    events: list[AppliedEventStatus]


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
    mandatory_report: MandatoryReportStatus
    applied_events: AppliedEventsStatus


class ActivitiesSummaryResponse(BaseModel):
    min_year: int
    max_year: int
    years: list[YearlyActivitySummary]
