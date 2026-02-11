import json
from uuid import UUID

from pywebpush import webpush, WebPushException

from app.core.config import settings
from app.core.database import supabase


def send_push_to_user(user_id: UUID, payload: dict) -> None:
    """Send a Web Push notification to all of a user's subscriptions.

    Silently skips if VAPID keys are not configured.
    Removes stale subscriptions (expired/unsubscribed endpoints).
    """
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return

    try:
        result = (
            supabase.table("push_subscriptions")
            .select("id, endpoint, p256dh, auth")
            .eq("user_id", str(user_id))
            .execute()
        )
    except Exception:
        return

    for sub in result.data or []:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {
                        "p256dh": sub["p256dh"],
                        "auth": sub["auth"],
                    },
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": settings.VAPID_SUBJECT,
                },
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                try:
                    supabase.table("push_subscriptions").delete().eq(
                        "id", sub["id"]
                    ).execute()
                except Exception:
                    pass
        except Exception:
            pass
