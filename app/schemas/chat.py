from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class ChatRoomType(str, Enum):
    DM = "DM"
    GROUP = "GROUP"


# ==========================================
# REQUEST SCHEMAS
# ==========================================


class MessageCreate(BaseModel):
    message: str | None = None
    file_urls: list[str] | None = None


# ==========================================
# RESPONSE SCHEMAS
# ==========================================


class ChatRoomMember(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None


class MessageResponse(BaseModel):
    id: UUID
    sender_id: UUID | None
    sender_name: str | None
    sender_avatar_url: str | None
    room_id: UUID
    sent_at: datetime
    message: str | None
    file_urls: list[str] | None


class ChatRoomResponse(BaseModel):
    id: UUID
    type: ChatRoomType
    created_at: datetime
    members: list[ChatRoomMember]
    club_id: UUID | None
    name: str | None
    image_url: str | None
    last_message: MessageResponse | None = None


class ChatRoomListResponse(BaseModel):
    rooms: list[ChatRoomResponse]


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool
