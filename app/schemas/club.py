from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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

    category: ClubCategory
    anonymity: ClubAnonymity


class ClubUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: ClubCategory | None = None
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
    category: ClubCategory
    anonymity: ClubAnonymity

    member_count: int
    created_at: datetime
    is_member: bool

    user_profile: UserClubProfile | None

    recent_member_images: list[str] | None

    model_config = ConfigDict(from_attributes=True)


class ClubListResponse(BaseModel):
    clubs: list[ClubResponse]
    total: int


class GalleryImageCreate(BaseModel):
    image_url: str
    caption: str | None = None


class GalleryImageResponse(BaseModel):
    id: UUID
    club_id: UUID
    image_url: str
    caption: str | None
    uploaded_by: UUID | None
    created_at: datetime


class GalleryListResponse(BaseModel):
    images: list[GalleryImageResponse]
    total: int


class ClubMember(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None = None


class ClubMemberListResponse(BaseModel):
    members: list[ClubMember]
    total: int
