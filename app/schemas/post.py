from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PostType(str, Enum):
    FEED = "FEED"
    NOTICE = "NOTICE"
    EVENT = "EVENT"


class EventStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ApplicationStatus(str, Enum):
    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PostAuthor(BaseModel):
    id: UUID
    name: str

    avatar_url: str | None = None
    is_following: bool = False


class FeedPostCreate(BaseModel):
    content: str
    is_anonymous: bool

    image_urls: list[str] | None = None


class NoticePostCreate(BaseModel):
    title: str
    content: str

    is_pinned: bool

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None


class EventPostCreate(BaseModel):
    title: str
    content: str

    application_start: datetime
    application_end: datetime
    event_start: datetime
    event_end: datetime
    event_location: str
    is_mandatory: bool

    event_category: str | None = None
    max_participants: int | None = None

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None


class FeedPostUpdate(BaseModel):
    content: str | None = None

    image_urls: list[str] | None = None


class NoticePostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None

    is_pinned: bool | None = None

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None


class EventPostUpdate(BaseModel):
    title: str | None = None
    content: str | None = None

    application_start: datetime | None = None
    application_end: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    event_location: str | None = None
    is_mandatory: bool | None = None

    event_category: str | None = None
    max_participants: int | None = None

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None


class FeedPostResponse(BaseModel):
    id: UUID
    type: Literal[PostType.FEED] = PostType.FEED
    created_at: datetime

    content: str
    is_anonymous: bool

    like_count: int
    scrap_count: int
    comment_count: int
    is_liked: bool
    is_scrapped: bool

    author: PostAuthor | None = None

    image_urls: list[str] | None = None

    class Config:
        from_attributes = True


class NoticePostResponse(BaseModel):
    id: UUID
    type: Literal[PostType.NOTICE] = PostType.NOTICE
    created_at: datetime

    title: str
    content: str
    is_pinned: bool

    view_count: int
    like_count: int
    is_liked: bool

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None

    class Config:
        from_attributes = True


class EventPostResponse(BaseModel):
    id: UUID
    type: Literal[PostType.EVENT] = PostType.EVENT
    created_at: datetime

    title: str
    content: str
    application_start: datetime | None
    application_end: datetime | None
    event_start: datetime
    event_end: datetime
    event_location: str
    is_mandatory: bool
    participants_count: int

    like_count: int
    comment_count: int
    is_liked: bool
    is_applied: bool = False

    event_status: EventStatus
    application_status: ApplicationStatus

    event_category: str | None = None
    max_participants: int | None = None

    file_urls: list[str] | None = None
    image_urls: list[str] | None = None

    class Config:
        from_attributes = True


class FeedPostListResponse(BaseModel):
    posts: list[FeedPostResponse]
    total: int


class NoticePostListResponse(BaseModel):
    posts: list[NoticePostResponse]
    total: int


class EventPostListResponse(BaseModel):
    posts: list[EventPostResponse]
    total: int
