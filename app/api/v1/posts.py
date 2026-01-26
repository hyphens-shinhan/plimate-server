from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.post import (
    PostType,
    FeedPostCreate,
    NoticePostCreate,
    EventPostCreate,
    PostUpdate,
    PostResponse,
    PostListResponse,
    PostAuthor,
)

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("/feed", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_feed_post(post: FeedPostCreate, user: AuthenticatedUser):
    result = (
        supabase.table("posts")
        .insert(
            {
                "author_id": str(user.id),
                "type": PostType.FEED.value,
                "content": post.content,
                "image_urls": post.image_urls,
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await get_post(result.data[0]["id"], user)


@router.post(
    "/notice", response_model=PostResponse, status_code=status.HTTP_201_CREATED
)
async def create_notice_post(post: NoticePostCreate, user: AuthenticatedUser):
    user_result = (
        supabase.table("users").select("role").eq("id", str(user.id)).single().execute()
    )

    if not user_result.data or user_result.data["role"] != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    result = (
        supabase.table("posts")
        .insert(
            {
                "author_id": str(user.id),
                "type": PostType.NOTICE.value,
                "content": post.content,
                "file_urls": post.file_urls,
                "image_urls": post.image_urls,
                "is_mandatory": post.is_mandatory,
                "is_pinned": post.is_pinned,
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await get_post(result.data[0]["id"], user)


@router.post("/event", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_event_post(post: EventPostCreate, user: AuthenticatedUser):
    result = (
        supabase.table("posts")
        .insert(
            {
                "author_id": str(user.id),
                "type": PostType.EVENT.value,
                "content": post.content,
                "event_date": post.event_date.isoformat(),
                "event_location": post.event_location,
                "file_urls": post.file_urls,
                "image_urls": post.image_urls,
                "is_mandatory": post.is_mandatory,
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return await get_post(result.data[0]["id"], user)


@router.get("", response_model=PostListResponse)
async def get_posts(
    user: AuthenticatedUser,
    post_type: PostType | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = (
        supabase.table("posts")
        .select(
            "*, users!posts_author_id_fkey(id, name, avatar_url)",
            count=CountMethod.exact,
        )
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    if post_type:
        query = query.eq("type", type)

    result = query.execute()

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
        author_data = row.pop("users", {}) or {}
        posts.append(
            PostResponse(
                id=row["id"],
                author=PostAuthor(**author_data) if author_data else None,
                type=row["type"],
                content=row.get("content"),
                file_urls=row.get("file_urls"),
                image_urls=row.get("image_urls"),
                event_date=row.get("event_date"),
                event_location=row.get("event_location"),
                event_status=row.get("event_status"),
                is_mandatory=row.get("is_mandatory", False),
                is_pinned=row.get("is_pinned", False),
                like_count=row.get("like_count", 0),
                comment_count=row.get("comment_count", 0),
                is_liked=row["id"] in liked_post_ids,
                created_at=row["created_at"],
            )
        )

    return PostListResponse(posts=posts, total=result.count or len(posts))


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("posts")
        .select("*, users!posts_author_id_fkey(id, name, avatar_url)")
        .eq("id", str(post_id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    row = result.data
    author_data = row.pop("users", {}) or {}

    liked_result = (
        supabase.table("post_interactions")
        .select("post_id")
        .eq("user_id", str(user.id))
        .eq("post_id", str(post_id))
        .eq("type", "LIKE")
        .execute()
    )

    return PostResponse(
        id=row["id"],
        author=PostAuthor(**author_data) if author_data else None,
        type=row["type"],
        content=row.get("content"),
        file_urls=row.get("file_urls"),
        image_urls=row.get("image_urls"),
        event_date=row.get("event_date"),
        event_location=row.get("event_location"),
        event_status=row.get("event_status"),
        is_mandatory=row.get("is_mandatory", False),
        is_pinned=row.get("is_pinned", False),
        like_count=row.get("like_count", 0),
        comment_count=row.get("comment_count", 0),
        is_liked=bool(liked_result.data),
        created_at=row["created_at"],
    )


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(post_id: UUID, updates: PostUpdate, user: AuthenticatedUser):
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

    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    if "event_date" in update_data and update_data["event_date"]:
        update_data["event_date"] = update_data["event_date"].isoformat()

    supabase.table("posts").update(update_data).eq("id", str(post_id)).execute()

    return await get_post(post_id, user)


@router.delete("/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(post_id: UUID, user: AuthenticatedUser):
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


@router.post("/{post_id}/like", status_code=status.HTTP_201_CREATED)
async def like_post(post_id: UUID, user: AuthenticatedUser):
    post = (
        supabase.table("posts").select("id").eq("id", str(post_id)).single().execute()
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    supabase.table("post_interactions").insert(
        {
            "user_id": str(user.id),
            "post_id": str(post_id),
            "type": "LIKE",
        }
    ).execute()

    supabase.rpc("increment_like_count", {"post_id": str(post_id)}).execute()

    return {"message": "Post liked successfully"}


@router.delete("/{post_id}/like", status_code=status.HTTP_200_OK)
async def unlike_post(post_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("post_interactions")
        .delete()
        .eq("user_id", str(user.id))
        .eq("post_id", str(post_id))
        .eq("type", "LIKE")
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    supabase.rpc("decrement_like_count", {"post_id": str(post_id)}).execute()

    return {"message": "Post unliked successfully"}
