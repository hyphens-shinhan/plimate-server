from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.notification import (
    NotificationType,
    NotificationActor,
    NotificationResponse,
    NotificationListResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _build_notification_response(row: dict) -> NotificationResponse:
    actor = None
    if row.get("actor_id") and row.get("users"):
        user_data = row["users"]
        actor = NotificationActor(
            id=user_data["id"],
            name=user_data["name"],
            avatar_url=user_data.get("avatar_url"),
        )

    return NotificationResponse(
        id=row["id"],
        type=NotificationType(row["type"]),
        recipient_id=row["recipient_id"],
        actor=actor,
        post_id=row.get("post_id"),
        comment_id=row.get("comment_id"),
        room_id=row.get("room_id"),
        club_id=row.get("club_id"),
        is_read=row["is_read"],
        created_at=row["created_at"],
    )


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
):
    try:
        query = (
            supabase.table("notifications")
            .select(
                "*, users!notifications_actor_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("recipient_id", str(user.id))
        )

        if unread_only:
            query = query.eq("is_read", False)

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        unread_result = (
            supabase.table("notifications")
            .select("id", count=CountMethod.exact)
            .eq("recipient_id", str(user.id))
            .eq("is_read", False)
            .execute()
        )

        return NotificationListResponse(
            notifications=[_build_notification_response(row) for row in result.data],
            total=result.count or 0,
            unread_count=unread_result.count or 0,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(user: AuthenticatedUser):
    try:
        supabase.table("notifications").update({"is_read": True}).eq(
            "recipient_id", str(user.id)
        ).eq("is_read", False).execute()

        return {"message": "All notifications marked as read"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(notification_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("notifications")
            .update({"is_read": True})
            .eq("id", str(notification_id))
            .eq("recipient_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return {"message": "Notification marked as read"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{notification_id}", status_code=status.HTTP_200_OK)
async def delete_notification(notification_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("notifications")
            .delete()
            .eq("id", str(notification_id))
            .eq("recipient_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return {"message": "Notification deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
