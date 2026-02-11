from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class AppRole(str, Enum):
    YB = "YB"
    YB_LEADER = "YB_LEADER"
    OB = "OB"
    MENTOR = "MENTOR"
    ADMIN = "ADMIN"


class ScholarshipType(str, Enum):
    GENERAL = "GENERAL"
    VETERAN_CHILD = "VETERAN_CHILD"
    SELF_RELIANCE = "SELF_RELIANCE"
    LAW_SCHOOL = "LAW_SCHOOL"
    EXCHANGE_STUDENT = "EXCHANGE_STUDENT"
    LEADER_DEVELOPMENT = "LEADER_DEVELOPMENT"


class UserHomeProfile(BaseModel):
    id: UUID
    name: str
    role: AppRole

    avatar_url: str | None = None

    affiliation: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    model_config = ConfigDict(from_attributes=True)


class UserPublicProfile(BaseModel):
    id: UUID
    name: str
    role: AppRole

    avatar_url: str | None = None
    email: str | None = None
    phone_number: str | None = None

    affiliation: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    bio: str | None = None
    interests: list[str] | None = None
    hobbies: list[str] | None = None

    address: str | None = None
    follow_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserMyProfile(BaseModel):
    id: UUID
    scholar_number: str
    name: str
    email: str
    role: AppRole

    avatar_url: str | None = None
    phone_number: str | None = None

    affiliation: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    bio: str | None = None
    interests: list[str] | None = None
    hobbies: list[str] | None = None

    address: str | None = None

    volunteer_hours: int = 0

    model_config = ConfigDict(from_attributes=True)


class UserPrivacySettings(BaseModel):
    is_location_public: bool
    is_contact_public: bool
    is_scholarship_public: bool
    is_follower_public: bool

    model_config = ConfigDict(from_attributes=True)


class UserPrivacyUpdate(BaseModel):
    is_location_public: bool | None = None
    is_contact_public: bool | None = None
    is_scholarship_public: bool | None = None
    is_follower_public: bool | None = None


class UserProfileUpdate(BaseModel):
    avatar_url: str | None = None
    phone_number: str | None = None

    affiliation: str | None = None
    major: str | None = None

    bio: str | None = None
    interests: list[str] | None = None
    hobbies: list[str] | None = None

    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    volunteer_hours: int | None = Field(None, ge=0, le=10000)


class ScholarshipEligibilityResponse(BaseModel):
    current_year: int
    gpa: float
    total_credits: float
    semester_breakdown: list[dict]
    volunteer_hours: int
    mandatory_total: int
    mandatory_completed: int


class MandatoryActivityStatus(BaseModel):
    id: UUID
    title: str
    due_date: date
    activity_type: str
    is_completed: bool


class MandatoryStatusResponse(BaseModel):
    year: int
    total: int
    completed: int
    activities: list[MandatoryActivityStatus]


class VolunteerHoursResponse(BaseModel):
    """Schema for volunteer hours response."""

    volunteer_hours: int

    model_config = ConfigDict(from_attributes=True)


class VolunteerHoursUpdate(BaseModel):
    """Schema for updating volunteer hours."""

    volunteer_hours: int = Field(
        ..., ge=0, le=10000, description="Total volunteer hours"
    )
