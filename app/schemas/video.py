from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class VideoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    url: str = Field(..., min_length=1)


class VideoResponse(BaseModel):
    id: UUID
    title: str
    url: str
    thumbnail_url: str | None = None
    created_at: datetime


class VideoListResponse(BaseModel):
    videos: list[VideoResponse]
    total: int
