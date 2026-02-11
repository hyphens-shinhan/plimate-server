from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class NotificationType(str, Enum):
    LIKE = "LIKE"
    COMMENT = "COMMENT"
    COMMENT_REPLY = "COMMENT_REPLY"
    CHAT_MESSAGE = "CHAT_MESSAGE"
    FOLLOW_REQUEST = "FOLLOW_REQUEST"
    FOLLOW_ACCEPT = "FOLLOW_ACCEPT"
    REPORT_EXPORT = "REPORT_EXPORT"
    MENTORING_REQUEST = "MENTORING_REQUEST"
    MENTORING_ACCEPTED = "MENTORING_ACCEPTED"


class NotificationActor(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None = None


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    recipient_id: UUID

    actor: NotificationActor | None = None

    post_id: UUID | None = None
    comment_id: UUID | None = None
    room_id: UUID | None = None
    club_id: UUID | None = None

    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    unread_count: int


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
