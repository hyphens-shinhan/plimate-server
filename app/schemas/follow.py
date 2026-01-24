from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class FollowStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class FollowUser(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None = None


class FollowRequest(BaseModel):
    id: UUID
    requester: FollowUser
    created_at: datetime


class FollowResponse(BaseModel):
    id: UUID
    requester_id: UUID
    receiver_id: UUID
    status: FollowStatus
    created_at: datetime
    accepted_at: datetime | None = None


class FollowListResponse(BaseModel):
    followers: list[FollowUser]
    total: int


class FollowRequestListResponse(BaseModel):
    requests: list[FollowRequest]
    total: int


class FollowStatusResponse(BaseModel):
    status: FollowStatus | None = None
    is_following: bool
