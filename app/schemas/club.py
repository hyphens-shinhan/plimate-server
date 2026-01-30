from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


from enum import StrEnum


class ClubCategory(StrEnum):
    GLOBAL = "GLOBAL"
    VOLUNTEER = "VOLUNTEER"
    STUDY = "STUDY"


class ClubCreate(BaseModel):
    name: str
    description: str

    category: list[ClubCategory]
    is_anonymous: bool


class ClubUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: list[ClubCategory] | None = None
    is_anonymous: bool | None = None


class ClubResponse(BaseModel):
    id: UUID
    creator_id: UUID

    name: str
    description: str
    category: list[ClubCategory]

    member_count: int
    created_at: datetime
    is_member: bool
    is_anonymous: bool

    recent_member_images: list[str] | None

    class Config:
        from_attributes = True


class ClubListResponse(BaseModel):
    clubs: list[ClubResponse]
    total: int
