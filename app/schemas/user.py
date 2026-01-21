from datetime import datetime, date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class AppRole(str, Enum):
    YB = "YB"
    OB = "OB"
    MENTOR = "MENTOR"
    ADMIN = "ADMIN"


class UserBase(BaseModel):
    id: UUID
    scholar_number: str | None = None
    name: str
    avatar_url: str | None = None
    role: AppRole = AppRole.YB
    created_at: datetime | None = None


class UserProfileBase(BaseModel):
    birth_date: str | None = None

    latitude: float | None = None
    longitude: float | None = None
    is_location_public: bool | None = None

    university: str | None = None
    major: str | None = None
    grade: int | None = None
    scholarship_type: str | None = None
    scholarship_batch: int | None = None
    gpa: float | None = None
    volunteer_hours: int = 0

    interests: list[str] | None = None
    hobbies: list[str] | None = None


class UserResponse(BaseModel):
    profile: UserProfileBase | None = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    scholar_number: str | None = None
    name: str
    avatar_url: str | None = None
    role: AppRole = AppRole.YB
    created_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    birth_date: str | None = None

    latitude: float | None = None
    longitude: float | None = None
    is_location_public: bool | None = None

    university: str | None = None
    major: str | None = None
    grade: int | None = Field(None, ge=1, le=6)
    scholarship_type: str | None = None
    scholarship_batch: int | None = None
    gpa: float | None = Field(None, ge=0.0, le=4.5)
    volunteer_hours: int | None = Field(None, ge=0)

    interests: list[str] | None = None
    hobbies: list[str] | None = None
