from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.post import (
    PostType,
    EventStatus,
    PostAuthor,
    FeedPostCreate,
    NoticePostCreate,
    EventPostCreate,
    FeedPostUpdate,
    NoticePostUpdate,
    EventPostUpdate,
    FeedPostResponse,
    NoticePostResponse,
    EventPostResponse,
    NoticePostListResponse,
    FeedPostListResponse,
    EventPostListResponse,
)

router = APIRouter(prefix="/posts", tags=["posts"])


def _build_feed_response(
    row: dict,
    author_data: dict,
    is_liked: bool,
    is_scrapped: bool,
    is_following: bool,
) -> FeedPostResponse:
    is_anonymous = row["is_anonymous"]

    author = None
    if not is_anonymous:
        author = PostAuthor(**author_data)
        author.is_following = is_following

    return FeedPostResponse(
        id=row["id"],
        created_at=row["created_at"],
        content=row["content"],
        is_anonymous=is_anonymous,
        like_count=row.get("like_count", 0),
        scrap_count=row.get("scrap_count", 0),
        comment_count=row.get("comment_count", 0),
        is_liked=is_liked,
        is_scrapped=is_scrapped,
        author=author,
        image_urls=row.get("image_urls"),
    )


def _build_notice_response(row: dict, is_liked: bool) -> NoticePostResponse:
    return NoticePostResponse(
        id=row["id"],
        created_at=row["created_at"],
        title=row["title"],
        content=row["content"],
        is_pinned=row.get("is_pinned", False),
        view_count=row.get("view_count", 0),
        like_count=row.get("like_count", 0),
        is_liked=is_liked,
        file_urls=row.get("file_urls"),
        image_urls=row.get("image_urls"),
    )


def _build_event_response(row: dict, is_liked: bool) -> EventPostResponse:
    return EventPostResponse(
        id=row["id"],
        created_at=row["created_at"],
        title=row["title"],
        content=row["content"],
        event_start=row["event_start"],
        event_end=row["event_end"],
        event_location=row["event_location"],
        is_mandatory=row.get("is_mandatory", False),
        participants_count=0,
        like_count=row.get("like_count"),
        comment_count=row.get("comment_count"),
        is_liked=is_liked,
        event_status=row["event_status"],
        event_category=row["event_category"],
        max_participants=row.get("max_participants"),
        file_urls=row.get("file_urls"),
        image_urls=row.get("image_urls"),
    )


@router.post(
    "/feed", response_model=FeedPostResponse, status_code=status.HTTP_201_CREATED
)
async def create_feed_post(post: FeedPostCreate, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("posts")
            .insert(
                {
                    "author_id": str(user.id),
                    "type": PostType.FEED.value,
                    "content": post.content,
                    "is_anonymous": post.is_anonymous,
                    "scrap_count": 0,
                    "image_urls": post.image_urls,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return await get_feed_post(result.data[0]["id"], user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/feed", response_model=FeedPostListResponse)
async def get_feed_posts(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        result = (
            supabase.table("posts")
            .select(
                "*, users!posts_author_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("type", PostType.FEED.value)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        interactions = (
            supabase.table("post_interactions")
            .select("post_id, type")
            .eq("user_id", str(user.id))
            .in_("type", ["LIKE", "SCRAP"])
            .execute()
        )
        liked_post_ids = {
            row["post_id"] for row in interactions.data if row["type"] == "LIKE"
        }
        scrapped_post_ids = {
            row["post_id"] for row in interactions.data if row["type"] == "SCRAP"
        }

        author_ids = {
            row["author_id"]
            for row in result.data
            if not row["is_anonymous"] and row["author_id"] and str(row["author_id"]) != str(user.id)
        }

        following_ids = set()
        if author_ids:
            follows_outgoing = (
                supabase.table("follows")
                .select("receiver_id")
                .eq("requester_id", str(user.id))
                .eq("status", "ACCEPTED")
                .in_("receiver_id", list(author_ids))
                .execute()
            )

            follows_incoming = (
                supabase.table("follows")
                .select("requester_id")
                .eq("receiver_id", str(user.id))
                .eq("status", "ACCEPTED")
                .in_("requester_id", list(author_ids))
                .execute()
            )

            following_ids = {row["receiver_id"] for row in follows_outgoing.data} | {
                row["requester_id"] for row in follows_incoming.data
            }

        posts = []
        for row in result.data:
            author_data = row.pop("users", {}) or {}
            is_following = row["author_id"] in following_ids or row["author_id"] == str(
                user.id
            )

            posts.append(
                _build_feed_response(
                    row,
                    author_data,
                    row["id"] in liked_post_ids,
                    row["id"] in scrapped_post_ids,
                    is_following,
                )
            )

        return FeedPostListResponse(posts=posts, total=result.count or len(posts))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/feed/anonymous", response_model=FeedPostListResponse)
async def get_feed_anonymous_posts(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        result = (
            supabase.table("posts")
            .select(
                "*, users!posts_author_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("type", PostType.FEED.value)
            .eq("is_anonymous", True)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        interactions = (
            supabase.table("post_interactions")
            .select("post_id, type")
            .eq("user_id", str(user.id))
            .in_("type", ["LIKE", "SCRAP"])
            .execute()
        )
        liked_post_ids = {
            row["post_id"] for row in interactions.data if row["type"] == "LIKE"
        }
        scrapped_post_ids = {
            row["post_id"] for row in interactions.data if row["type"] == "SCRAP"
        }

        posts = []
        for row in result.data:
            author_data = row.pop("users", {}) or {}
            posts.append(
                _build_feed_response(
                    row,
                    author_data,
                    row["id"] in liked_post_ids,
                    row["id"] in scrapped_post_ids,
                    True,
                )
            )

        return FeedPostListResponse(posts=posts, total=result.count or len(posts))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/feed/{post_id}", response_model=FeedPostResponse)
async def get_feed_post(
    post_id: UUID,
    user: AuthenticatedUser,
):
    try:
        result = (
            supabase.table("posts")
            .select("*, users!posts_author_id_fkey(id, name, avatar_url)")
            .eq("id", str(post_id))
            .eq("type", PostType.FEED.value)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        row = result.data
        author_data = row.pop("users", {}) or {}

        interactions = (
            supabase.table("post_interactions")
            .select("type")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .in_("type", ["LIKE", "SCRAP"])
            .execute()
        )
        is_liked = any(i["type"] == "LIKE" for i in interactions.data)
        is_scrapped = any(i["type"] == "SCRAP" for i in interactions.data)

        is_following = str(row["author_id"]) == str(user.id)
        if not row["is_anonymous"] and not is_following:
            check = (
                supabase.table("follows")
                .select("id")
                .eq("status", "ACCEPTED")
                .or_(
                    f"and(requester_id.eq.{user.id},receiver_id.eq.{row['author_id']}),"
                    f"and(requester_id.eq.{row['author_id']},receiver_id.eq.{user.id})"
                )
                .maybe_single()
                .execute()
            )
            is_following = bool(check.data)

        return _build_feed_response(
            row, author_data, is_liked, is_scrapped, is_following
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/feed/{post_id}", response_model=FeedPostResponse)
async def update_feed_post(
    post_id: UUID,
    updates: FeedPostUpdate,
    user: AuthenticatedUser,
):
    try:
        existing = (
            supabase.table("posts")
            .select("author_id, type")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data or existing.data["type"] != "FEED":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if existing.data["author_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        supabase.table("posts").update(update_data).eq("id", str(post_id)).execute()

        return await get_feed_post(post_id, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/notice", response_model=NoticePostResponse, status_code=status.HTTP_201_CREATED
)
async def create_notice_post(post: NoticePostCreate, user: AuthenticatedUser):
    try:
        user_result = (
            supabase.table("users")
            .select("role")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        if not user_result.data or user_result.data["role"] != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        result = (
            supabase.table("posts")
            .insert(
                {
                    "author_id": str(user.id),
                    "type": PostType.NOTICE.value,
                    "title": post.title,
                    "content": post.content,
                    "is_pinned": post.is_pinned,
                    "file_urls": post.file_urls,
                    "image_urls": post.image_urls,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return await get_notice_post(result.data[0]["id"], user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/notice", response_model=NoticePostListResponse)
async def get_notice_posts(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        result = (
            supabase.table("posts")
            .select(
                "*, users!posts_author_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("type", PostType.NOTICE.value)
            .order("is_pinned", desc=True)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("type", "LIKE")
            .execute()
        )
        liked_post_ids = {row.pop("post_id") for row in liked_result.data}

        posts = []
        for row in result.data:
            posts.append(_build_notice_response(row, row["id"] in liked_post_ids))

        return NoticePostListResponse(posts=posts, total=result.count or len(posts))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/notice/{post_id}", response_model=NoticePostResponse)
async def get_notice_post(post_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("posts")
            .select("*, users!posts_author_id_fkey(id, name, avatar_url)")
            .eq("id", str(post_id))
            .eq("type", PostType.NOTICE.value)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        row = result.data

        supabase.table("posts").update({"view_count": row.get("view_count", 0) + 1}).eq(
            "id", str(post_id)
        ).execute()

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .eq("type", "LIKE")
            .execute()
        )

        return _build_notice_response(row, bool(liked_result.data))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/notice/{post_id}", response_model=NoticePostResponse)
async def update_notice_post(
    post_id: UUID, updates: NoticePostUpdate, user: AuthenticatedUser
):
    try:
        user_result = (
            supabase.table("users")
            .select("role")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        if not user_result.data or user_result.data["role"] != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        existing = (
            supabase.table("posts")
            .select("id, type")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data or existing.data["type"] != "NOTICE":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        supabase.table("posts").update(update_data).eq("id", str(post_id)).execute()

        return await get_notice_post(post_id, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/event", response_model=EventPostResponse, status_code=status.HTTP_201_CREATED
)
async def create_event_post(post: EventPostCreate, user: AuthenticatedUser):
    try:
        user_result = (
            supabase.table("users")
            .select("role")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        if not user_result.data or user_result.data["role"] != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        result = (
            supabase.table("posts")
            .insert(
                {
                    "author_id": str(user.id),
                    "type": PostType.EVENT.value,
                    "title": post.title,
                    "content": post.content,
                    "event_start": post.event_start.isoformat(),
                    "event_end": post.event_end.isoformat(),
                    "event_location": post.event_location,
                    "event_category": post.event_category,
                    "max_participants": post.max_participants,
                    "file_urls": post.file_urls,
                    "image_urls": post.image_urls,
                    "is_mandatory": post.is_mandatory,
                    "event_status": (
                        EventStatus.SCHEDULED.value
                        if datetime.now(timezone.utc) < post.event_start
                        else (
                            EventStatus.CLOSED.value
                            if datetime.now(timezone.utc) > post.event_end
                            else EventStatus.OPEN.value
                        )
                    ),
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return await get_event_post(result.data[0]["id"], user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/event", response_model=EventPostListResponse)
async def get_event_posts(
    user: AuthenticatedUser,
    event_status: EventStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        query = (
            supabase.table("posts")
            .select(
                "*, users!posts_author_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("type", PostType.EVENT.value)
        )

        if event_status:
            query = (
                query.eq("event_status", event_status.value)
                .order("event_end", desc=False)
                .range(offset, offset + limit - 1)
            )
            result = query.execute()
        else:
            result = query.execute()
            data = result.data

            status_priority = {
                EventStatus.OPEN.value: 1,
                EventStatus.SCHEDULED.value: 2,
                EventStatus.CLOSED.value: 3,
            }

            def sort_key(x):
                return (
                    status_priority.get(x.get("event_status"), 99),
                    x.get("event_end"),
                )

            data.sort(key=sort_key)

            total_count = len(data)
            sliced_data = data[offset : offset + limit]

            result.data = sliced_data
            result.count = total_count

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("type", "LIKE")
            .execute()
        )
        liked_post_ids = {row["post_id"] for row in liked_result.data}

        posts = []
        for row in result.data:
            posts.append(_build_event_response(row, row["id"] in liked_post_ids))

        return EventPostListResponse(posts=posts, total=result.count or len(posts))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/event/{post_id}", response_model=EventPostResponse)
async def get_event_post(post_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("posts")
            .select("*, users!posts_author_id_fkey(id, name, avatar_url)")
            .eq("id", str(post_id))
            .eq("type", PostType.EVENT.value)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        row = result.data

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .eq("type", "LIKE")
            .execute()
        )

        return _build_event_response(row, bool(liked_result.data))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/event/{post_id}", response_model=EventPostResponse)
async def update_event_post(
    post_id: UUID, updates: EventPostUpdate, user: AuthenticatedUser
):
    try:
        user_result = (
            supabase.table("users")
            .select("role")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        if not user_result.data or user_result.data["role"] != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        existing = (
            supabase.table("posts")
            .select("author_id, type")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data or existing.data["type"] != "EVENT":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if existing.data["author_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        if "event_start" in update_data and update_data["event_start"]:
            update_data["event_start"] = update_data["event_start"].isoformat()
        if "event_end" in update_data and update_data["event_end"]:
            update_data["event_end"] = update_data["event_end"].isoformat()

        supabase.table("posts").update(update_data).eq("id", str(post_id)).execute()

        return await get_event_post(post_id, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(post_id: UUID, user: AuthenticatedUser):
    try:
        existing = (
            supabase.table("posts")
            .select("author_id")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if existing.data["author_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        supabase.table("posts").delete().eq("id", str(post_id)).execute()

        return {"message": "Post deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{post_id}/like", status_code=status.HTTP_200_OK)
async def toggle_like(post_id: UUID, user: AuthenticatedUser):
    try:
        post = (
            supabase.table("posts")
            .select("id, like_count")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not post.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        existing = (
            supabase.table("post_interactions")
            .select("user_id")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .eq("type", "LIKE")
            .execute()
        )

        if existing.data:
            supabase.table("post_interactions").delete().eq("user_id", str(user.id)).eq(
                "post_id", str(post_id)
            ).eq("type", "LIKE").execute()
            new_count = max(0, post.data["like_count"] - 1)
            supabase.table("posts").update({"like_count": new_count}).eq(
                "id", str(post_id)
            ).execute()

            return {"liked": False, "like_count": new_count}
        else:
            supabase.table("post_interactions").insert(
                {
                    "user_id": str(user.id),
                    "post_id": str(post_id),
                    "type": "LIKE",
                }
            ).execute()

        new_count = post.data["like_count"] + 1
        supabase.table("posts").update({"like_count": new_count}).eq(
            "id", str(post_id)
        ).execute()

        return {"liked": True, "like_count": new_count}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{post_id}/scrap", status_code=status.HTTP_200_OK)
async def toggle_scrap(post_id: UUID, user: AuthenticatedUser):
    try:
        post = (
            supabase.table("posts")
            .select("id, scrap_count, type")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not post.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if post.data["type"] != PostType.FEED.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        existing = (
            supabase.table("post_interactions")
            .select("user_id")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .eq("type", "SCRAP")
            .execute()
        )

        if existing.data:
            supabase.table("post_interactions").delete().eq("user_id", str(user.id)).eq(
                "post_id", str(post_id)
            ).eq("type", "SCRAP").execute()
            new_count = max(0, post.data["scrap_count"] - 1)
            supabase.table("posts").update({"scrap_count": new_count}).eq(
                "id", str(post_id)
            ).execute()

            return {"scrapped": False, "scrap_count": new_count}
        else:
            supabase.table("post_interactions").insert(
                {
                    "user_id": str(user.id),
                    "post_id": str(post_id),
                    "type": "SCRAP",
                }
            ).execute()

        new_count = post.data["scrap_count"] + 1
        supabase.table("posts").update({"scrap_count": new_count}).eq(
            "id", str(post_id)
        ).execute()

        return {"scrapped": True, "scrap_count": new_count}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
