from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.core.notifications import create_notification
from app.schemas.notification import NotificationType
from app.schemas.post import (
    PostType,
    EventStatus,
    ApplicationStatus,
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
    MyPostItem,
    MyPostItemType,
    MyPostsResponse,
)
from app.schemas.report import PublicReportResponse, PublicAttendanceResponse

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


def _compute_application_status(row: dict) -> ApplicationStatus:
    now = datetime.now(timezone.utc)
    if now < datetime.fromisoformat(row["application_start"]):
        return ApplicationStatus.UPCOMING
    if now > datetime.fromisoformat(row["application_end"]):
        return ApplicationStatus.CLOSED
    return ApplicationStatus.OPEN


def _compute_event_status(row: dict) -> EventStatus:
    now = datetime.now(timezone.utc)
    if now < datetime.fromisoformat(row["event_start"]):
        return EventStatus.SCHEDULED
    if now > datetime.fromisoformat(row["event_end"]):
        return EventStatus.CLOSED
    return EventStatus.OPEN


def _build_event_response(
    row: dict, is_liked: bool, participants_count: int = 0, is_applied: bool = False
) -> EventPostResponse:
    return EventPostResponse(
        id=row["id"],
        created_at=row["created_at"],
        title=row["title"],
        content=row["content"],
        application_start=row.get("application_start"),
        application_end=row.get("application_end"),
        event_start=row["event_start"],
        event_end=row["event_end"],
        event_location=row["event_location"],
        is_mandatory=row.get("is_mandatory", False),
        participants_count=participants_count,
        like_count=row.get("like_count"),
        comment_count=row.get("comment_count"),
        is_liked=is_liked,
        is_applied=is_applied,
        event_status=_compute_event_status(row),
        application_status=_compute_application_status(row),
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
                    "file_urls": post.file_urls,
                    "file_names": post.file_names,
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


@router.get("/me", response_model=MyPostsResponse)
async def get_my_posts(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get posts written by the current user.
    Includes:
    - Feed posts authored by the user
    - Council report posts authored by the user (as council leader)
    """
    try:
        # Get user's feed and council report posts
        result = (
            supabase.table("posts")
            .select("id, type, created_at, title, content, image_urls, like_count, comment_count")
            .eq("author_id", str(user.id))
            .in_("type", [PostType.FEED.value, PostType.COUNCIL_REPORT.value])
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        # Get total count
        count_result = (
            supabase.table("posts")
            .select("id", count="exact")
            .eq("author_id", str(user.id))
            .in_("type", [PostType.FEED.value, PostType.COUNCIL_REPORT.value])
            .execute()
        )

        posts = []
        for row in result.data or []:
            post_type = MyPostItemType.FEED if row["type"] == "FEED" else MyPostItemType.COUNCIL_REPORT
            posts.append(
                MyPostItem(
                    id=row["id"],
                    type=post_type,
                    created_at=row["created_at"],
                    title=row.get("title"),
                    content=row.get("content"),
                    image_urls=row.get("image_urls"),
                    like_count=row.get("like_count", 0),
                    comment_count=row.get("comment_count", 0),
                )
            )

        return MyPostsResponse(posts=posts, total=count_result.count or len(posts))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/user/{user_id}", response_model=MyPostsResponse)
async def get_user_public_posts(
    user_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Get public posts written by a specific user (for public profile view).
    Excludes anonymous posts.
    Includes:
    - Feed posts that are not anonymous
    - Council report posts authored by the user
    """
    try:
        # Get user's non-anonymous feed and council report posts
        result = (
            supabase.table("posts")
            .select("id, type, created_at, title, content, image_urls, like_count, comment_count, is_anonymous")
            .eq("author_id", str(user_id))
            .in_("type", [PostType.FEED.value, PostType.COUNCIL_REPORT.value])
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        # Filter out anonymous posts on the application level
        # (Council reports are never anonymous, but feed posts can be)
        filtered_data = [
            row for row in (result.data or [])
            if row["type"] == PostType.COUNCIL_REPORT.value or not row.get("is_anonymous", False)
        ]

        # Get total count (excluding anonymous)
        count_result = (
            supabase.table("posts")
            .select("id, type, is_anonymous")
            .eq("author_id", str(user_id))
            .in_("type", [PostType.FEED.value, PostType.COUNCIL_REPORT.value])
            .execute()
        )
        total_count = sum(
            1 for row in (count_result.data or [])
            if row["type"] == PostType.COUNCIL_REPORT.value or not row.get("is_anonymous", False)
        )

        posts = []
        for row in filtered_data:
            post_type = MyPostItemType.FEED if row["type"] == "FEED" else MyPostItemType.COUNCIL_REPORT
            posts.append(
                MyPostItem(
                    id=row["id"],
                    type=post_type,
                    created_at=row["created_at"],
                    title=row.get("title"),
                    content=row.get("content"),
                    image_urls=row.get("image_urls"),
                    like_count=row.get("like_count", 0),
                    comment_count=row.get("comment_count", 0),
                )
            )

        return MyPostsResponse(posts=posts, total=total_count)
    except HTTPException:
        raise
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
            if not row["is_anonymous"]
            and row["author_id"]
            and str(row["author_id"]) != str(user.id)
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
            is_following = check is not None and check.data is not None

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
                    "file_names": post.file_names,
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
                    "application_start": post.application_start.isoformat(),
                    "application_end": post.application_end.isoformat(),
                    "event_start": post.event_start.isoformat(),
                    "event_end": post.event_end.isoformat(),
                    "event_location": post.event_location,
                    "event_category": post.event_category,
                    "max_participants": post.max_participants,
                    "file_urls": post.file_urls,
                    "image_urls": post.image_urls,
                    "is_mandatory": post.is_mandatory,
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

        result = query.execute()
        data = result.data

        if event_status:
            data = [row for row in data if _compute_event_status(row) == event_status]

        status_priority = {
            EventStatus.OPEN: 1,
            EventStatus.SCHEDULED: 2,
            EventStatus.CLOSED: 3,
        }

        data.sort(
            key=lambda x: (
                status_priority.get(_compute_event_status(x), 99),
                x.get("event_end"),
            )
        )

        total_count = len(data)
        result.data = data[offset : offset + limit]
        result.count = total_count

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("type", "LIKE")
            .execute()
        )
        liked_post_ids = {row["post_id"] for row in liked_result.data}

        event_ids = [row["id"] for row in result.data]
        applied_result = (
            (
                supabase.table("event_participants")
                .select("post_id")
                .eq("user_id", str(user.id))
                .in_("post_id", event_ids)
                .execute()
            )
            if event_ids
            else type("R", (), {"data": []})()
        )
        applied_post_ids = {row["post_id"] for row in (applied_result.data or [])}

        participant_counts_result = (
            (
                supabase.table("event_participants")
                .select("post_id")
                .in_("post_id", event_ids)
                .execute()
            )
            if event_ids
            else type("R", (), {"data": []})()
        )
        participant_counts: dict[str, int] = {}
        for row in participant_counts_result.data or []:
            participant_counts[row["post_id"]] = (
                participant_counts.get(row["post_id"], 0) + 1
            )

        posts = []
        for row in result.data:
            posts.append(
                _build_event_response(
                    row,
                    row["id"] in liked_post_ids,
                    participant_counts.get(row["id"], 0),
                    row["id"] in applied_post_ids,
                )
            )

        return EventPostListResponse(posts=posts, total=result.count or len(posts))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/event/me/applied", response_model=EventPostListResponse)
async def get_my_applied_events(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        applications = (
            supabase.table("event_participants")
            .select("post_id", count=CountMethod.exact)
            .eq("user_id", str(user.id))
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        if not applications.data:
            return EventPostListResponse(posts=[], total=0)

        post_ids = [a["post_id"] for a in applications.data]

        result = (
            supabase.table("posts")
            .select("*")
            .in_("id", post_ids)
            .eq("type", PostType.EVENT.value)
            .execute()
        )

        liked_result = (
            supabase.table("post_interactions")
            .select("post_id")
            .eq("user_id", str(user.id))
            .eq("type", "LIKE")
            .in_("post_id", post_ids)
            .execute()
        )
        liked_post_ids = {row["post_id"] for row in liked_result.data}

        participant_counts_result = (
            supabase.table("event_participants")
            .select("post_id")
            .in_("post_id", post_ids)
            .execute()
        )
        participant_counts: dict[str, int] = {}
        for row in participant_counts_result.data or []:
            participant_counts[row["post_id"]] = (
                participant_counts.get(row["post_id"], 0) + 1
            )

        post_map = {row["id"]: row for row in (result.data or [])}
        posts = []
        for pid in post_ids:
            if pid in post_map:
                posts.append(
                    _build_event_response(
                        post_map[pid],
                        pid in liked_post_ids,
                        participant_counts.get(pid, 0),
                        is_applied=True,
                    )
                )

        return EventPostListResponse(
            posts=posts, total=applications.count or len(posts)
        )
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

        participants = (
            supabase.table("event_participants")
            .select("user_id", count=CountMethod.exact)
            .eq("post_id", str(post_id))
            .execute()
        )
        participants_count = participants.count or 0

        is_applied = any(
            p["user_id"] == str(user.id) for p in (participants.data or [])
        )

        return _build_event_response(
            row, bool(liked_result.data), participants_count, is_applied
        )
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

        for dt_field in (
            "application_start",
            "application_end",
            "event_start",
            "event_end",
        ):
            if dt_field in update_data and update_data[dt_field]:
                update_data[dt_field] = update_data[dt_field].isoformat()

        supabase.table("posts").update(update_data).eq("id", str(post_id)).execute()

        return await get_event_post(post_id, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/council", response_model=list[PublicReportResponse])
async def get_public_reports_feed(
    user: AuthenticatedUser,
    limit: int = 20,
    offset: int = 0,
):
    """
    Get public reports for the feed.
    Returns submitted reports marked as public, ordered by submission date.
    Excludes receipts for privacy, includes attendance.
    """
    try:
        # Fetch public, submitted reports with council info and leader
        reports_result = (
            supabase.table("activity_reports")
            .select("*, councils(id, affiliation, region, year, leader_id, users!councils_leader_id_fkey(id, name, avatar_url))")
            .eq("is_public", True)
            .eq("is_submitted", True)
            .order("submitted_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        reports = reports_result.data or []
        report_ids = [r["id"] for r in reports]

        # Fetch all associated posts for these reports
        posts_result = (
            supabase.table("posts")
            .select("id, report_id, like_count, comment_count, scrap_count")
            .in_("report_id", report_ids)
            .execute()
        ) if report_ids else None

        # Map report_id to post data
        report_to_post = {}
        if posts_result and posts_result.data:
            for p in posts_result.data:
                report_to_post[p["report_id"]] = p

        # Fetch user interactions
        post_ids = [p["id"] for p in (posts_result.data or [])] if posts_result else []
        liked_post_ids = set()
        scrapped_post_ids = set()
        if post_ids:
            interactions = (
                supabase.table("post_interactions")
                .select("post_id, type")
                .eq("user_id", str(user.id))
                .in_("post_id", post_ids)
                .execute()
            )
            liked_post_ids = {row["post_id"] for row in interactions.data if row["type"] == "LIKE"}
            scrapped_post_ids = {row["post_id"] for row in interactions.data if row["type"] == "SCRAP"}

        # Build response with attendance
        result = []
        for report in reports:
            council = report.get("councils", {}) or {}
            leader = council.get("users", {}) or {}
            report_id = report["id"]

            # Fetch attendance with user names - only PRESENT status
            attendance_result = (
                supabase.table("activity_attendance")
                .select("*, users(name)")
                .eq("report_id", report_id)
                .eq("status", "PRESENT")
                .execute()
            )

            attendance = [
                PublicAttendanceResponse(
                    name=(
                        a.get("users", {}).get("name", "Unknown")
                        if a.get("users")
                        else "Unknown"
                    ),
                )
                for a in (attendance_result.data or [])
            ]

            # Build author object if leader exists
            author = None
            if leader.get("id"):
                author = PostAuthor(
                    id=leader["id"],
                    name=leader.get("name", "Unknown"),
                    avatar_url=leader.get("avatar_url"),
                    is_following=False,  # Can be computed if needed
                )

            # Get post data for this report
            post_data = report_to_post.get(report_id, {})
            post_id = post_data.get("id")

            # Skip reports without an associated post (shouldn't happen for public reports)
            if not post_id:
                continue

            result.append(
                PublicReportResponse(
                    id=post_id,  # Primary ID for all interactions
                    report_id=report["id"],  # Original report ID for admin ops
                    title=report["title"],
                    activity_date=report.get("activity_date"),
                    location=report.get("location"),
                    content=report.get("content"),
                    image_urls=report.get("image_urls"),
                    attendance=attendance,
                    submitted_at=report["submitted_at"],
                    author=author,
                    like_count=post_data.get("like_count") or 0,
                    comment_count=post_data.get("comment_count") or 0,
                    scrap_count=post_data.get("scrap_count") or 0,
                    is_liked=post_id in liked_post_ids if post_id else False,
                    is_scrapped=post_id in scrapped_post_ids if post_id else False,
                )
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/council/{post_id}", response_model=PublicReportResponse)
async def get_council_report_detail(
    post_id: UUID,
    user: AuthenticatedUser,
):
    """
    Get a single public council report by its post ID.
    Returns the report with author, attendance, counts, and user interaction state.
    """
    try:
        # First fetch the post to get report_id and counts
        post_result = (
            supabase.table("posts")
            .select("id, report_id, like_count, comment_count, scrap_count, author_id")
            .eq("id", str(post_id))
            .eq("type", PostType.COUNCIL_REPORT.value)
            .maybe_single()
            .execute()
        )

        post_data = (post_result.data if post_result else None) or {}
        report_id = post_data.get("report_id")

        if not report_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Council report not found",
            )

        # Fetch the report with council info and leader
        report_result = (
            supabase.table("activity_reports")
            .select("*, councils(id, affiliation, region, year, leader_id, users!councils_leader_id_fkey(id, name, avatar_url))")
            .eq("id", str(report_id))
            .eq("is_public", True)
            .eq("is_submitted", True)
            .single()
            .execute()
        )

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found or not public",
            )

        report = report_result.data
        council = report.get("councils", {}) or {}
        leader = council.get("users", {}) or {}

        # Fetch attendance with user names - only PRESENT status
        attendance_result = (
            supabase.table("activity_attendance")
            .select("*, users(name)")
            .eq("report_id", str(report_id))
            .eq("status", "PRESENT")
            .execute()
        )

        attendance = [
            PublicAttendanceResponse(
                name=(
                    a.get("users", {}).get("name", "Unknown")
                    if a.get("users")
                    else "Unknown"
                ),
            )
            for a in (attendance_result.data or [])
        ]

        # Build author object if leader exists
        author = None
        if leader.get("id"):
            author = PostAuthor(
                id=leader["id"],
                name=leader.get("name", "Unknown"),
                avatar_url=leader.get("avatar_url"),
                is_following=False,
            )

        # Fetch user interactions
        is_liked = False
        is_scrapped = False
        interactions = (
            supabase.table("post_interactions")
            .select("type")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .execute()
        )
        is_liked = any(i["type"] == "LIKE" for i in (interactions.data or []))
        is_scrapped = any(i["type"] == "SCRAP" for i in (interactions.data or []))

        return PublicReportResponse(
            id=post_id,  # Primary ID for all interactions
            report_id=report["id"],  # Original report ID for admin ops
            title=report["title"],
            activity_date=report.get("activity_date"),
            location=report.get("location"),
            content=report.get("content"),
            image_urls=report.get("image_urls"),
            attendance=attendance,
            submitted_at=report["submitted_at"],
            author=author,
            like_count=post_data.get("like_count") or 0,
            comment_count=post_data.get("comment_count") or 0,
            scrap_count=post_data.get("scrap_count") or 0,
            is_liked=is_liked,
            is_scrapped=is_scrapped,
        )
    except HTTPException:
        raise
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
            .select("id, author_id, like_count")
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

            create_notification(
                recipient_id=UUID(post.data["author_id"]),
                notification_type=NotificationType.LIKE,
                actor_id=user.id,
                post_id=post_id,
            )

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

        if post.data["type"] not in [PostType.FEED.value, PostType.COUNCIL_REPORT.value]:
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
            new_count = max(0, (post.data["scrap_count"] or 0) - 1)
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

        new_count = (post.data["scrap_count"] or 0) + 1
        supabase.table("posts").update({"scrap_count": new_count}).eq(
            "id", str(post_id)
        ).execute()

        return {"scrapped": True, "scrap_count": new_count}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/event/{post_id}/apply", status_code=status.HTTP_201_CREATED)
async def apply_for_event(post_id: UUID, user: AuthenticatedUser):
    try:
        post = (
            supabase.table("posts")
            .select("id, type, application_start, application_end, max_participants")
            .eq("id", str(post_id))
            .eq("type", PostType.EVENT.value)
            .single()
            .execute()
        )

        if not post.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        app_status = _compute_application_status(post.data)
        if app_status != ApplicationStatus.OPEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Application period is not open",
            )

        existing = (
            supabase.table("event_participants")
            .select("user_id")
            .eq("post_id", str(post_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already applied for this event",
            )

        if post.data.get("max_participants"):
            current_count = (
                supabase.table("event_participants")
                .select("user_id", count=CountMethod.exact)
                .eq("post_id", str(post_id))
                .execute()
            )
            if (current_count.count or 0) >= post.data["max_participants"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Event has reached maximum participants",
                )

        supabase.table("event_participants").insert(
            {"post_id": str(post_id), "user_id": str(user.id)}
        ).execute()

        return {"message": "Successfully applied for event"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/event/{post_id}/apply", status_code=status.HTTP_200_OK)
async def cancel_event_application(post_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("event_participants")
            .delete()
            .eq("post_id", str(post_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No application found for this event",
            )

        return {"message": "Event application cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
