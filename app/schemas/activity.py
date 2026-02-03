from uuid import UUID

from pydantic import BaseModel


class CouncilReportStatus(BaseModel):
    title: str | None = None
    is_completed: bool


class AcademicReportStatus(BaseModel):
    is_completed: bool


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


class ActivitiesSummaryResponse(BaseModel):
    min_year: int
    max_year: int
    years: list[YearlyActivitySummary]
