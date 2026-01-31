from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.chat import (
    ChatRoomType,
    MessageCreate,
    ChatRoomMember,
    ChatRoomResponse,
    ChatRoomListResponse,
    MessageResponse,
    MessageListResponse,
)

router = APIRouter(prefix="/chats", tags=["chats"])

DEFAULT_PAGE_SIZE = 30


async def _check_mutual_follow(user_id: str, target_user_id: str):
    """Verify that two users have an ACCEPTED follow relationship in either direction."""
    try:
        result = (
            supabase.table("follows")
            .select("id")
            .or_(
                f"and(requester_id.eq.{user_id},receiver_id.eq.{target_user_id}),"
                f"and(requester_id.eq.{target_user_id},receiver_id.eq.{user_id})"
            )
            .eq("status", "ACCEPTED")
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only message mutual followers",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify follow status: {str(e)}",
        )


async def _check_not_blocked(user_id: str, target_user_id: str):
    """Verify that neither user has blocked the other."""
    try:
        result = (
            supabase.table("blocks")
            .select("blocker_id")
            .or_(
                f"and(blocker_id.eq.{user_id},blocked_id.eq.{target_user_id}),"
                f"and(blocker_id.eq.{target_user_id},blocked_id.eq.{user_id})"
            )
            .execute()
        )

        if result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot message this user",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify block status: {str(e)}",
        )


async def _check_room_member(user_id: str, room_id: str):
    """Verify that the user is a member of the chat room."""
    try:
        result = (
            supabase.table("chat_room_members")
            .select("user_id")
            .eq("room_id", room_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this chat room",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify room membership: {str(e)}",
        )


async def _check_club_member(user_id: str, club_id: str):
    """Verify that the user is a member of the club."""
    try:
        result = (
            supabase.table("club_members")
            .select("user_id")
            .eq("club_id", club_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a club member to access this chat",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify club membership: {str(e)}",
        )


def _resolve_club_member_identity(
    sender_id: str, club_members_data: list[dict]
) -> tuple[str | None, str | None]:
    """Resolve sender display name and avatar using club member identity."""
    for cm in club_members_data:
        if cm.get("user_id") == sender_id:
            if cm.get("member_nickname"):
                return cm["member_nickname"], cm.get("member_avatar_url")
            user_data = cm.get("users") or {}
            return user_data.get("name"), user_data.get("avatar_url")
    return None, None


def _build_room_response(
    room: dict, members: list[dict], last_message: dict | None = None
) -> ChatRoomResponse:
    member_list = []
    for m in members:
        user_data = m.get("users")
        if user_data:
            member_list.append(ChatRoomMember(**user_data))

    msg_response = None
    if last_message:
        sender = last_message.get("users")
        msg_response = MessageResponse(
            id=last_message["id"],
            sender_id=last_message.get("sender_id"),
            sender_name=sender.get("name") if sender else None,
            sender_avatar_url=sender.get("avatar_url") if sender else None,
            room_id=last_message["room_id"],
            message=last_message.get("message"),
            file_urls=last_message.get("file_urls"),
            sent_at=last_message["sent_at"],
        )

    return ChatRoomResponse(
        id=room["id"],
        type=room["type"],
        club_id=room.get("club_id"),
        name=room.get("name"),
        image_url=room.get("image_url"),
        created_at=room["created_at"],
        members=member_list,
        last_message=msg_response,
    )


def _build_club_room_response(
    room: dict, club_members_data: list[dict], last_message: dict | None = None
) -> ChatRoomResponse:
    """Build room response using club member identities."""
    member_list = []
    for cm in club_members_data:
        if cm.get("member_nickname"):
            member_list.append(
                ChatRoomMember(
                    id=cm["user_id"],
                    name=cm["member_nickname"],
                    avatar_url=cm.get("member_avatar_url"),
                )
            )
        else:
            user_data = cm.get("users") or {}
            member_list.append(
                ChatRoomMember(
                    id=cm["user_id"],
                    name=user_data.get("name", "Unknown"),
                    avatar_url=user_data.get("avatar_url"),
                )
            )

    msg_response = None
    if last_message:
        sender_name, sender_avatar = _resolve_club_member_identity(
            last_message.get("sender_id"), club_members_data
        )
        msg_response = MessageResponse(
            id=last_message["id"],
            sender_id=last_message.get("sender_id"),
            sender_name=sender_name,
            sender_avatar_url=sender_avatar,
            room_id=last_message["room_id"],
            message=last_message.get("message"),
            file_urls=last_message.get("file_urls"),
            sent_at=last_message["sent_at"],
        )

    return ChatRoomResponse(
        id=room["id"],
        type=room["type"],
        club_id=room.get("club_id"),
        name=room.get("name"),
        image_url=room.get("image_url"),
        created_at=room["created_at"],
        members=member_list,
        last_message=msg_response,
    )


@router.post(
    "/message/{user_id}",
    response_model=ChatRoomResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_get_message(target_user_id: UUID, user: AuthenticatedUser):
    """
    Create a DM room with a user, or return the existing one.
    Requires mutual follow and no blocks.
    """
    if target_user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a DM with yourself",
        )

    await _check_not_blocked(str(user.id), str(target_user_id))
    await _check_mutual_follow(str(user.id), str(target_user_id))

    try:
        # Check if DM room already exists between these two users
        my_rooms = (
            supabase.table("chat_room_members")
            .select("room_id")
            .eq("user_id", str(user.id))
            .execute()
        )

        if my_rooms.data:
            my_room_ids = [r["room_id"] for r in my_rooms.data]

            for room_id in my_room_ids:
                room_check = (
                    supabase.table("chat_rooms")
                    .select("*, chat_room_members!inner(user_id)")
                    .eq("id", room_id)
                    .eq("type", "DM")
                    .eq("chat_room_members.user_id", str(target_user_id))
                    .execute()
                )

                if room_check.data:
                    existing_room = room_check.data[0]
                    members = (
                        supabase.table("chat_room_members")
                        .select("user_id, users!inner(id, name, avatar_url)")
                        .eq("room_id", existing_room["id"])
                        .execute()
                    )
                    return _build_room_response(existing_room, members.data or [])

        # Create new DM room
        room_result = (
            supabase.table("chat_rooms")
            .insert({"type": ChatRoomType.DM.value, "created_by": str(user.id)})
            .execute()
        )

        if not room_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create DM room",
            )

        new_room = room_result.data[0]

        supabase.table("chat_room_members").insert(
            [
                {"room_id": new_room["id"], "user_id": str(user.id)},
                {"room_id": new_room["id"], "user_id": str(target_user_id)},
            ]
        ).execute()

        members = (
            supabase.table("chat_room_members")
            .select("user_id, users!inner(id, name, avatar_url)")
            .eq("room_id", new_room["id"])
            .execute()
        )

        return _build_room_response(new_room, members.data or [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/clubs/{club_id}/join", response_model=ChatRoomResponse)
async def join_club_chat(club_id: UUID, user: AuthenticatedUser):
    """
    Join the club's chat room. Creates the room if it doesn't exist yet.
    Requires club membership.
    """
    await _check_club_member(str(user.id), str(club_id))

    try:
        # Get or create the club's chat room
        room_result = (
            supabase.table("chat_rooms")
            .select("*")
            .eq("club_id", str(club_id))
            .maybe_single()
            .execute()
        )

        if room_result and room_result.data:
            room = room_result.data
        else:
            # Fetch club info for room name/image
            club = (
                supabase.table("clubs")
                .select("name, image_url")
                .eq("id", str(club_id))
                .single()
                .execute()
            )

            room_insert = (
                supabase.table("chat_rooms")
                .insert(
                    {
                        "type": ChatRoomType.GROUP.value,
                        "club_id": str(club_id),
                        "name": club.data["name"] if club.data else None,
                        "image_url": club.data.get("image_url") if club.data else None,
                        "created_by": str(user.id),
                    }
                )
                .execute()
            )

            if not room_insert.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create club chat room",
                )
            room = room_insert.data[0]

        # Check if already a chat member
        existing = (
            supabase.table("chat_room_members")
            .select("user_id")
            .eq("room_id", room["id"])
            .eq("user_id", str(user.id))
            .execute()
        )

        if not existing.data:
            supabase.table("chat_room_members").insert(
                {"room_id": room["id"], "user_id": str(user.id)}
            ).execute()

        # Fetch club members who are in the chat for identity resolution
        chat_member_ids_result = (
            supabase.table("chat_room_members")
            .select("user_id")
            .eq("room_id", room["id"])
            .execute()
        )
        chat_member_ids = [m["user_id"] for m in (chat_member_ids_result.data or [])]

        club_members_data = (
            supabase.table("club_members")
            .select(
                "user_id, member_nickname, member_avatar_url, users!inner(id, name, avatar_url)"
            )
            .eq("club_id", str(club_id))
            .in_("user_id", chat_member_ids)
            .execute()
        ).data or []

        return _build_club_room_response(room, club_members_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/clubs/{club_id}/leave")
async def leave_club_chat(club_id: UUID, user: AuthenticatedUser):
    """Leave the club's chat room."""
    try:
        room_result = (
            supabase.table("chat_rooms")
            .select("id")
            .eq("club_id", str(club_id))
            .maybe_single()
            .execute()
        )

        if not room_result or not room_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Club chat room not found",
            )

        result = (
            supabase.table("chat_room_members")
            .delete()
            .eq("room_id", room_result.data["id"])
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not in this chat room",
            )

        return {"message": "Left club chat successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("", response_model=ChatRoomListResponse)
async def get_chat_rooms(user: AuthenticatedUser):
    """
    List all chat rooms the user is a member of.
    Ordered by most recent message.
    """
    try:
        memberships = (
            supabase.table("chat_room_members")
            .select("room_id")
            .eq("user_id", str(user.id))
            .execute()
        )

        if not memberships.data:
            return ChatRoomListResponse(rooms=[])

        room_ids = [m["room_id"] for m in memberships.data]

        rooms_result = (
            supabase.table("chat_rooms").select("*").in_("id", room_ids).execute()
        )

        rooms = []
        for room in rooms_result.data or []:
            # Fetch last message
            last_msg_result = (
                supabase.table("chat_messages")
                .select("*, users!sender_id(name, avatar_url)")
                .eq("room_id", room["id"])
                .order("sent_at", desc=True)
                .limit(1)
                .execute()
            )
            last_message = last_msg_result.data[0] if last_msg_result.data else None

            if room["type"] == ChatRoomType.GROUP.value and room.get("club_id"):
                # Club chat: use club member identities
                chat_member_ids_result = (
                    supabase.table("chat_room_members")
                    .select("user_id")
                    .eq("room_id", room["id"])
                    .execute()
                )
                chat_member_ids = [
                    m["user_id"] for m in (chat_member_ids_result.data or [])
                ]

                club_members_data = (
                    supabase.table("club_members")
                    .select(
                        "user_id, member_nickname, member_avatar_url, users!inner(id, name, avatar_url)"
                    )
                    .eq("club_id", room["club_id"])
                    .in_("user_id", chat_member_ids)
                    .execute()
                ).data or []

                rooms.append(
                    _build_club_room_response(room, club_members_data, last_message)
                )
            else:
                # DM: use real identities
                members = (
                    supabase.table("chat_room_members")
                    .select("user_id, users!inner(id, name, avatar_url)")
                    .eq("room_id", room["id"])
                    .execute()
                )
                rooms.append(
                    _build_room_response(room, members.data or [], last_message)
                )

        rooms.sort(
            key=lambda r: r.last_message.sent_at if r.last_message else r.created_at,
            reverse=True,
        )

        return ChatRoomListResponse(rooms=rooms)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/clubs/{club_id}/messages", response_model=MessageListResponse)
async def get_club_chat_messages(
    club_id: UUID,
    user: AuthenticatedUser,
    cursor: str | None = Query(None, description="Message ID to paginate from"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
):
    """
    Get paginated messages for a club chat.
    Uses club member identity (anonymous nickname/avatar when set).
    """
    try:
        # Find the club's chat room
        room_result = (
            supabase.table("chat_rooms")
            .select("id, club_id")
            .eq("club_id", str(club_id))
            .maybe_single()
            .execute()
        )

        if not room_result or not room_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Club chat room not found",
            )

        room_id = room_result.data["id"]
        await _check_room_member(str(user.id), room_id)

        # Fetch messages
        query = (
            supabase.table("chat_messages")
            .select("*")
            .eq("room_id", room_id)
            .order("sent_at", desc=True)
            .limit(limit + 1)
        )

        if cursor:
            cursor_msg = (
                supabase.table("chat_messages")
                .select("sent_at")
                .eq("id", cursor)
                .single()
                .execute()
            )
            if cursor_msg.data:
                query = query.lt("sent_at", cursor_msg.data["sent_at"])

        result = query.execute()
        messages_data = result.data or []

        has_more = len(messages_data) > limit
        if has_more:
            messages_data = messages_data[:limit]

        # Fetch club member identities for all senders
        sender_ids = list({m["sender_id"] for m in messages_data if m.get("sender_id")})
        club_members_data = []
        if sender_ids:
            club_members_data = (
                supabase.table("club_members")
                .select(
                    "user_id, member_nickname, member_avatar_url, users!inner(id, name, avatar_url)"
                )
                .eq("club_id", str(club_id))
                .in_("user_id", sender_ids)
                .execute()
            ).data or []

        messages = []
        for msg in messages_data:
            sender_name, sender_avatar = _resolve_club_member_identity(
                msg.get("sender_id"), club_members_data
            )
            messages.append(
                MessageResponse(
                    id=msg["id"],
                    sender_id=msg.get("sender_id"),
                    sender_name=sender_name,
                    sender_avatar_url=sender_avatar,
                    room_id=msg["room_id"],
                    message=msg.get("message"),
                    file_urls=msg.get("file_urls"),
                    sent_at=msg["sent_at"],
                )
            )

        return MessageListResponse(messages=messages, has_more=has_more)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{room_id}/messages", response_model=MessageListResponse)
async def get_messages(
    room_id: UUID,
    user: AuthenticatedUser,
    cursor: str | None = Query(None, description="Message ID to paginate from"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
):
    """
    Get paginated messages for a chat room.
    Uses cursor-based pagination (pass last message ID as cursor).
    """
    await _check_room_member(str(user.id), str(room_id))

    try:
        query = (
            supabase.table("chat_messages")
            .select("*, users!sender_id(name, avatar_url)")
            .eq("room_id", str(room_id))
            .order("sent_at", desc=True)
            .limit(limit + 1)
        )

        if cursor:
            cursor_msg = (
                supabase.table("chat_messages")
                .select("sent_at")
                .eq("id", cursor)
                .single()
                .execute()
            )

            if cursor_msg.data:
                query = query.lt("sent_at", cursor_msg.data["sent_at"])

        result = query.execute()
        messages_data = result.data or []

        has_more = len(messages_data) > limit
        if has_more:
            messages_data = messages_data[:limit]

        messages = []
        for msg in messages_data:
            sender = msg.get("users")
            messages.append(
                MessageResponse(
                    id=msg["id"],
                    sender_id=msg.get("sender_id"),
                    sender_name=sender.get("name") if sender else None,
                    sender_avatar_url=sender.get("avatar_url") if sender else None,
                    room_id=msg["room_id"],
                    message=msg.get("message"),
                    file_urls=msg.get("file_urls"),
                    sent_at=msg["sent_at"],
                )
            )

        return MessageListResponse(messages=messages, has_more=has_more)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/{room_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(room_id: UUID, msg: MessageCreate, user: AuthenticatedUser):
    """
    Send a message to a chat room.
    Must provide at least message text or file_urls.
    """
    if not msg.message and not msg.file_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must contain text or files",
        )

    await _check_room_member(str(user.id), str(room_id))

    try:
        message_data = {
            "sender_id": str(user.id),
            "room_id": str(room_id),
            "message": msg.message,
            "file_urls": msg.file_urls,
        }

        result = supabase.table("chat_messages").insert(message_data).execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send message",
            )

        new_msg = result.data[0]

        # Fetch sender info
        sender_result = (
            supabase.table("users")
            .select("name, avatar_url")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        sender = sender_result.data if sender_result.data else {}

        return MessageResponse(
            id=new_msg["id"],
            sender_id=new_msg.get("sender_id"),
            sender_name=sender.get("name"),
            sender_avatar_url=sender.get("avatar_url"),
            room_id=new_msg["room_id"],
            message=new_msg.get("message"),
            file_urls=new_msg.get("file_urls"),
            sent_at=new_msg["sent_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
