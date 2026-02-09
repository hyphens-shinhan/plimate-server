from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CommentAuthor(BaseModel):
    id: UUID
    name: str

    avatar_url: str | None = None


class CommentCreate(BaseModel):
    content: str
    is_anonymous: bool

    parent_id: UUID | None = None


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: UUID
    post_id: UUID

    content: str
    is_anonymous: bool
    is_deleted: bool
    created_at: datetime

    author: CommentAuthor | None = None
    parent_id: UUID | None = None

    replies: list["CommentResponse"] = []

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    comments: list[CommentResponse]
    total: int


class CommentPseudonymResponse(BaseModel):
    pseudonym: str
    avatar_url: str
    is_locked: bool  # True if already locked for this post
