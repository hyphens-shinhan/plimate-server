from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


from enum import StrEnum


class ClubCategory(StrEnum):
    GLOBAL = "GLOBAL"
    VOLUNTEER = "VOLUNTEER"
    STUDY = "STUDY"


class ClubAnonymity(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    BOTH = "BOTH"


class ClubCreate(BaseModel):
    name: str
    description: str

    category: list[ClubCategory]
    anonymity: ClubAnonymity


class ClubUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: list[ClubCategory] | None = None
    anonymity: ClubAnonymity | None = None


class UserClubProfile(BaseModel):
    is_anonymous: bool | None = None

    nickname: str | None = None
    avatar_url: str | None = None


class ClubResponse(BaseModel):
    id: UUID
    creator_id: UUID

    name: str
    description: str
    category: list[ClubCategory]
    anonymity: ClubAnonymity

    member_count: int
    created_at: datetime
    is_member: bool

    user_profile: UserClubProfile | None

    recent_member_images: list[str] | None

    class Config:
        from_attributes = True


class ClubListResponse(BaseModel):
    clubs: list[ClubResponse]
    total: int
