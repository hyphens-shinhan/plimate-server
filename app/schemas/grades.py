from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class LetterGrade(str, Enum):
    """Valid letter grades with GPA mapping."""

    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C_PLUS = "C+"
    C = "C"
    D_PLUS = "D+"
    D = "D"
    F = "F"

    @property
    def gpa_value(self) -> float:
        """Get GPA value for this grade."""
        grade_map = {
            "A+": 4.5,
            "A": 4.0,
            "B+": 3.5,
            "B": 3.0,
            "C+": 2.5,
            "C": 2.0,
            "D+": 1.5,
            "D": 1.0,
            "F": 0.0,
        }
        return grade_map[self.value]


class Semester(int, Enum):
    """Semester enumeration."""

    SPRING = 1
    FALL = 2


class SemesterGradeCreate(BaseModel):
    """Schema for creating a new semester grade."""

    year: int = Field(..., ge=2000, le=2100)
    semester: Semester
    course_name: str = Field(..., min_length=1, max_length=200)
    grade: LetterGrade
    credits: int

    @field_validator("course_name")
    @classmethod
    def validate_course_name(cls, v: str) -> str:
        return v.strip()


class SemesterGradeResponse(BaseModel):
    """Schema for semester grade response."""

    id: UUID
    user_id: UUID
    year: int
    semester: Semester
    course_name: str
    grade: LetterGrade
    credits: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SemesterGradeListResponse(BaseModel):
    """Schema for list of semester grades."""

    grades: list[SemesterGradeResponse]
    total: int


class YearGPAResponse(BaseModel):
    """Schema for GPA calculation response."""

    year: int
    total_credits: float
    gpa: float
    semester_breakdown: list[dict]  # [{semester: 1, credits: 15, gpa: 3.8}]
    grades: list[SemesterGradeResponse]
