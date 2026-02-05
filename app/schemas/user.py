from enum import Enum
from uuid import UUID

from pydantic import BaseModel


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

    class Config:
        from_attributes = True


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

    location: str | None = None
    address: str | None = None

    class Config:
        from_attributes = True


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

    location: str | None = None
    address: str | None = None

    class Config:
        from_attributes = True


class UserPrivacySettings(BaseModel):
    is_location_public: bool
    is_contact_public: bool
    is_scholarship_public: bool
    is_follower_public: bool

    class Config:
        from_attributes = True


class UserPrivacyUpdate(BaseModel):
    is_location_public: bool | None = None
    is_contact_public: bool | None = None
    is_scholarship_public: bool | None = None
    is_follower_public: bool | None = None


class UserProfileUpdate(BaseModel):
    avatar_url: str | None = None
    email: str | None = None
    phone_number: str | None = None

    affiliation: str | None = None
    major: str | None = None

    bio: str | None = None
    interests: list[str] | None = None
    hobbies: list[str] | None = None

    location: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
