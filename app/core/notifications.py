from uuid import UUID

from app.core.database import supabase
from app.schemas.notification import NotificationType


def create_notification(
    recipient_id: UUID,
    notification_type: NotificationType,
    message: str | None = None,
    actor_id: UUID | None = None,
    post_id: UUID | None = None,
    comment_id: UUID | None = None,
    room_id: UUID | None = None,
    club_id: UUID | None = None,
) -> None:
    if actor_id and str(actor_id) == str(recipient_id):
        return

    try:
        supabase.table("notifications").insert(
            {
                "recipient_id": str(recipient_id),
                "type": notification_type.value,
                "message": message if message else None,
                "actor_id": str(actor_id) if actor_id else None,
                "post_id": str(post_id) if post_id else None,
                "comment_id": str(comment_id) if comment_id else None,
                "room_id": str(room_id) if room_id else None,
                "club_id": str(club_id) if club_id else None,
            }
        ).execute()
    except Exception:
        pass
