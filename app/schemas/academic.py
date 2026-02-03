from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class AcademicGoalCategory(str, Enum):
    MAJOR_REVIEW = "MAJOR_REVIEW"
    ENGLISH_STUDY = "ENGLISH_STUDY"
    CERTIFICATION_PREP = "CERTIFICATION_PREP"
    STUDY_GROUP = "STUDY_GROUP"
    ASSIGNMENT_EXAM_PREP = "ASSIGNMENT_EXAM_PREP"
    OTHER = "OTHER"


class GoalCreate(BaseModel):
    category: AcademicGoalCategory
    custom_category: str | None = None
    content: str
    achievement_pct: int | None = Field(None, ge=0, le=100)


class GoalResponse(BaseModel):
    id: UUID
    category: AcademicGoalCategory
    custom_category: str | None = None
    content: str
    achievement_pct: int | None


class AcademicReportCreate(BaseModel):
    year: int
    month: int = Field(..., ge=1, le=12)
    goals: list[GoalCreate] = Field(..., min_length=2)
    evidence_urls: list[str] | None = None


class AcademicReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    year: int
    month: int
    submitted_at: datetime
    evidence_urls: list[str] | None
    goals: list[GoalResponse]


class AcademicReportListResponse(BaseModel):
    reports: list[AcademicReportResponse]
    total: int


class AcademicReportUpdate(BaseModel):
    goals: list[GoalCreate] = Field(..., min_length=2)
    evidence_urls: list[str] | None = None


class AcademicReportLookupResponse(BaseModel):
    exists: bool
    report: AcademicReportResponse | None = None
