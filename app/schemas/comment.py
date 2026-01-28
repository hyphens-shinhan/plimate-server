from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
    created_at: datetime

    author: CommentAuthor | None = None
    parent_id: UUID | None = None

    replies: list["CommentResponse"] = []

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    comments: list[CommentResponse]
    total: int
