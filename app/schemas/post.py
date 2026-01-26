from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class PostType(str, Enum):
    FEED = "FEED"
    NOTICE = "NOTICE"
    EVENT = "EVENT"


class EventStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PostAuthor(BaseModel):
    id: UUID
    name: str
    avatar_url: str


class FeedPostCreate(BaseModel):
    content: str
    image_urls: list[str] | None = None


class NoticePostCreate(BaseModel):
    content: str
    file_urls: list[str] | None = None
    image_urls: list[str] | None = None
    is_mandatory: bool
    is_pinned: bool


class EventPostCreate(BaseModel):
    content: str
    event_date: datetime
    event_location: str
    file_urls: list[str] | None = None
    image_urls: list[str] | None = None
    is_mandatory: bool = False


class PostUpdate(BaseModel):
    content: str | None = None
    file_urls: list[str] | None = None
    image_urls: list[str] | None = None
    event_data: datetime | None = None
    event_location: str | None = None
    event_status: EventStatus | None = None
    is_mandatory: bool = False
    is_pinned: bool = False


class PostResponse(BaseModel):
    id: UUID
    author: PostAuthor
    type: PostType

    content: str | None = None
    file_urls: list[str] | None = None
    image_urls: list[str] | None = None

    event_date: datetime | None = None
    event_location: str | None = None
    event_status: EventStatus | None = None

    is_mandatory: bool = False
    is_pinned: bool = False

    like_count: int = 0
    comment_count: int = 0

    is_liked: bool = False

    created_at: datetime | None = None

    class Config:
        from_attributes = True


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    total: int
