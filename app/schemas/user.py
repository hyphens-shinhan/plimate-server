from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class AppRole(str, Enum):
    YB = "YB"
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
    avatar_url: str
    role: AppRole

    school: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    class Config:
        from_attributes = True


class UserPublicProfile(BaseModel):
    id: UUID
    name: str
    avatar_url: str
    role: AppRole

    email: str | None = None

    school: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    interests: list[str] | None = None
    hobbies: list[str] | None = None

    class Config:
        from_attributes = True


class UserFullProfile(BaseModel):
    id: UUID
    scholar_number: str
    name: str
    email: str
    avatar_url: str
    role: AppRole

    birth_date: str

    is_location_public: bool
    is_contact_public: bool
    is_scholarship_public: bool
    is_follower_public: bool

    school: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    interests: list[str] | None = None
    hobbies: list[str] | None = None

    latitude: float | None = None
    longitude: float | None = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    school: str | None = None
    major: str | None = None
    scholarship_type: ScholarshipType | None = None
    scholarship_batch: int | None = None

    birth_date: str | None = None
    interests: list[str] | None = None
    hobbies: list[str] | None = None

    latitude: float | None = None
    longitude: float | None = None

    is_location_public: bool | None = None
    is_contact_public: bool | None = None
    is_scholarship_public: bool | None = None
    is_follower_public: bool | None = None
