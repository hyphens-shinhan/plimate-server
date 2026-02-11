from uuid import UUID

from app.core.database import supabase
from app.core.push import send_push_to_user
from app.schemas.notification import NotificationType

_PUSH_TITLES = {
    NotificationType.LIKE: "좋아요",
    NotificationType.COMMENT: "새 댓글",
    NotificationType.COMMENT_REPLY: "새 답글",
    NotificationType.CHAT_MESSAGE: "새 메시지",
    NotificationType.FOLLOW_REQUEST: "팔로우 요청",
    NotificationType.FOLLOW_ACCEPT: "팔로우 수락",
    NotificationType.MENTORING_REQUEST: "멘토링 요청",
    NotificationType.MENTORING_ACCEPTED: "멘토링 수락",
}

_PUSH_BODIES = {
    NotificationType.LIKE: "회원님의 게시글에 좋아요를 눌렀습니다.",
    NotificationType.COMMENT: "회원님의 게시글에 댓글을 남겼습니다.",
    NotificationType.COMMENT_REPLY: "회원님의 댓글에 답글을 남겼습니다.",
    NotificationType.CHAT_MESSAGE: "새로운 메시지가 도착했습니다.",
    NotificationType.FOLLOW_REQUEST: "회원님에게 팔로우를 요청했습니다.",
    NotificationType.FOLLOW_ACCEPT: "회원님의 팔로우 요청을 수락했습니다.",
    NotificationType.MENTORING_REQUEST: "새로운 멘토링 요청이 도착했습니다.",
    NotificationType.MENTORING_ACCEPTED: "멘토링 요청이 수락되었습니다.",
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
        "title": _PUSH_TITLES.get(notification_type, "알림"),
        "body": message or _PUSH_BODIES.get(notification_type, "새로운 알림이 있습니다."),
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
