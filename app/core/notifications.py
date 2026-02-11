from uuid import UUID

from app.core.database import supabase
from app.core.push import send_push_to_user
from app.schemas.notification import NotificationType

_PUSH_TITLES = {
    NotificationType.LIKE: "New Like",
    NotificationType.COMMENT: "New Comment",
    NotificationType.COMMENT_REPLY: "New Reply",
    NotificationType.CHAT_MESSAGE: "New Message",
    NotificationType.FOLLOW_REQUEST: "Follow Request",
    NotificationType.FOLLOW_ACCEPT: "Follow Accepted",
    NotificationType.MENTORING_REQUEST: "Mentoring Request",
    NotificationType.MENTORING_ACCEPTED: "Mentoring Accepted",
}

_PUSH_BODIES = {
    NotificationType.LIKE: "Someone liked your post.",
    NotificationType.COMMENT: "Someone commented on your post.",
    NotificationType.COMMENT_REPLY: "Someone replied to your comment.",
    NotificationType.CHAT_MESSAGE: "You have a new message.",
    NotificationType.FOLLOW_REQUEST: "Someone wants to follow you.",
    NotificationType.FOLLOW_ACCEPT: "Your follow request was accepted.",
    NotificationType.MENTORING_REQUEST: "You received a mentoring request.",
    NotificationType.MENTORING_ACCEPTED: "Your mentoring request was accepted.",
}


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

    payload = {
        "type": notification_type.value,
        "title": _PUSH_TITLES.get(notification_type, "Notification"),
        "body": message or _PUSH_BODIES.get(notification_type, "You have a new notification."),
    }
    if post_id:
        payload["post_id"] = str(post_id)
    if room_id:
        payload["room_id"] = str(room_id)
    if club_id:
        payload["club_id"] = str(club_id)

    try:
        send_push_to_user(recipient_id, payload)
    except Exception:
        pass
