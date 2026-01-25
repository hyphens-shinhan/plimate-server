from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BlockedUser(BaseModel):
    id: UUID
    name: str
    avatar_url: str
    blocked_at: datetime


class BlockListResponse(BaseModel):
    users: list[BlockedUser]
    total: int
