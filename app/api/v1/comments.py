from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.core.notifications import create_notification
from app.core.nickname import generate_nickname, get_avatar_url
from app.schemas.notification import NotificationType
from app.schemas.comment import (
    CommentAuthor,
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
)

router = APIRouter(prefix="/posts/{post_id}/comments", tags=["comments"])


@router.get("/pseudonym")
async def generate_comment_pseudonym(post_id: UUID, user: AuthenticatedUser):
    """
    Generate pseudonym for anonymous comment.
    Returns locked identity if exists, otherwise generates preview.
    Allows reroll before first comment is submitted.
    """
    # Check for existing locked identity
    try:
        existing_result = (
            supabase.table("anonymous_comment_identities")
            .select("pseudonym, avatar_url")
            .eq("user_id", str(user.id))
            .eq("post_id", str(post_id))
            .execute()
        )
        existing_data = existing_result.data[0] if existing_result.data else None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking pseudonym: {str(e)}",
        )

    if existing_data:
        return {
            "pseudonym": existing_data["pseudonym"],
            "avatar_url": get_avatar_url(existing_data["avatar_url"]),
            "is_locked": True,
        }

    # Generate preview (not yet locked)
    pseudonym, avatar_id = generate_nickname()
    return {
        "pseudonym": pseudonym,
        "avatar_url": get_avatar_url(avatar_id),
        "is_locked": False,
    }


def _process_comment_row(
    row: dict, identity_map: dict | None = None
) -> CommentResponse:
    is_anonymous = row["is_anonymous"]
    is_deleted = row["is_deleted"]

    author = None
    if not is_deleted:
        if is_anonymous:
            # Fetch locked pseudonym for anonymous comment
            post_id = row["post_id"]
            author_id = row["author_id"]

            # Use provided identity_map if available (batch fetching), otherwise query
            if identity_map is not None:
                identity_data = identity_map.get((author_id, post_id))
            else:
                try:
                    identity_result = (
                        supabase.table("anonymous_comment_identities")
                        .select("pseudonym, avatar_url")
                        .eq("user_id", author_id)
                        .eq("post_id", post_id)
                        .execute()
                    )
                    identity_data = (
                        identity_result.data[0] if identity_result.data else None
                    )
                except Exception:
                    identity_data = None

            if identity_data:
                author = CommentAuthor(
                    id=author_id,  # Keep for moderation
                    name=identity_data["pseudonym"],
                    avatar_url=get_avatar_url(identity_data["avatar_url"]),
                )
        else:
            # Non-anonymous: show real author
            if user_data := (row.get("users") or {}):
                author = CommentAuthor(**user_data)

    return CommentResponse(
        id=row["id"],
        post_id=row["post_id"],
        content=row["content"],
        is_anonymous=is_anonymous,
        is_deleted=is_deleted,
        created_at=row["created_at"],
        author=author,
        parent_id=row.get("parent_id"),
        replies=[],
    )


@router.post("", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: UUID, comment: CommentCreate, user: AuthenticatedUser
):
    try:
        post = (
            supabase.table("posts")
            .select("id, author_id")
            .eq("id", str(post_id))
            .single()
            .execute()
        )

        if not post.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if comment.parent_id:
            parent = (
                supabase.table("post_comments")
                .select("id, author_id")
                .eq("id", str(comment.parent_id))
                .eq("post_id", str(post_id))
                .single()
                .execute()
            )
            if not parent.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent comment not found",
                )

        # Lock pseudonym for anonymous comments
        if comment.is_anonymous:
            # Check if identity already locked for this post
            try:
                identity_result = (
                    supabase.table("anonymous_comment_identities")
                    .select("pseudonym, avatar_url")
                    .eq("user_id", str(user.id))
                    .eq("post_id", str(post_id))
                    .execute()
                )
                identity_data = (
                    identity_result.data[0] if identity_result.data else None
                )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error checking pseudonym lock: {str(e)}",
                )

            if not identity_data:
                # First anonymous comment on this post - lock in new identity
                pseudonym, avatar = generate_nickname()

                try:
                    insert_result = (
                        supabase.table("anonymous_comment_identities")
                        .insert(
                            {
                                "user_id": str(user.id),
                                "post_id": str(post_id),
                                "pseudonym": pseudonym,
                                "avatar_url": avatar,
                            }
                        )
                        .execute()
                    )
                    if not insert_result.data:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to lock pseudonym for anonymous comment",
                        )
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error locking pseudonym: {str(e)}",
                    )
            # If identity_data exists, it's already locked - just proceed

        result = (
            supabase.table("post_comments")
            .insert(
                {
                    "post_id": str(post_id),
                    "author_id": str(user.id),
                    "content": comment.content,
                    "is_anonymous": comment.is_anonymous,
                    "parent_id": str(comment.parent_id) if comment.parent_id else None,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        supabase.rpc("increment_comment_count", {"post_id": str(post_id)}).execute()

        new_comment_id = UUID(result.data[0]["id"])
        if comment.parent_id:
            create_notification(
                recipient_id=UUID(parent.data["author_id"]),
                notification_type=NotificationType.COMMENT_REPLY,
                actor_id=user.id,
                comment_id=new_comment_id,
                post_id=post_id,
            )
        else:
            create_notification(
                recipient_id=UUID(post.data["author_id"]),
                notification_type=NotificationType.COMMENT,
                actor_id=user.id,
                comment_id=new_comment_id,
                post_id=post_id,
            )

        return await get_comment(post_id, result.data[0]["id"], user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("", response_model=CommentListResponse)
async def get_comments(
    post_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get comments for a post."""
    try:
        roots_query = (
            supabase.table("post_comments")
            .select(
                "*, users!post_comments_author_id_fkey(id, name, avatar_url)",
                count="exact",
            )
            .eq("post_id", str(post_id))
            .is_("parent_id", "null")
            .order("created_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute()
        )

        root_comments = roots_query.data
        total_count = roots_query.count or 0

        if not root_comments:
            return CommentListResponse(comments=[], total=total_count)

        root_ids = [c["id"] for c in root_comments]
        replies_query = (
            supabase.table("post_comments")
            .select("*, users!post_comments_author_id_fkey(id, name, avatar_url)")
            .eq("post_id", str(post_id))
            .in_("parent_id", root_ids)
            .order("created_at", desc=False)
            .execute()
        )

        replies_data = replies_query.data

        # Batch fetch anonymous comment identities to avoid N+1 queries
        all_comments = root_comments + replies_data
        anon_authors = {
            (comment["author_id"], comment["post_id"])
            for comment in all_comments
            if comment.get("is_anonymous")
        }

        identity_map = {}
        if anon_authors:
            user_ids = list(set(uid for uid, _ in anon_authors))
            identities = (
                supabase.table("anonymous_comment_identities")
                .select("user_id, post_id, pseudonym, avatar_url")
                .in_("user_id", user_ids)
                .eq("post_id", str(post_id))
                .execute()
            )

            identity_map = {
                (row["user_id"], row["post_id"]): row for row in (identities.data or [])
            }

        replies_map = {}

        for reply in replies_data:
            p_id = reply["parent_id"]
            if p_id not in replies_map:
                replies_map[p_id] = []
            replies_map[p_id].append(_process_comment_row(reply, identity_map))

        final_comments = []
        for root in root_comments:
            comment_obj = _process_comment_row(root, identity_map)
            if root["id"] in replies_map:
                comment_obj.replies = replies_map[root["id"]]
            final_comments.append(comment_obj)

        return CommentListResponse(comments=final_comments, total=total_count)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{comment_id}", response_model=CommentResponse)
async def get_comment(post_id: UUID, comment_id: UUID, user: AuthenticatedUser):
    """Get a single comment."""
    try:
        result = (
            supabase.table("post_comments")
            .select("*, users!post_comments_author_id_fkey(id, name, avatar_url)")
            .eq("id", str(comment_id))
            .eq("post_id", str(post_id))
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        row = result.data
        return _process_comment_row(row)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    post_id: UUID, comment_id: UUID, updates: CommentUpdate, user: AuthenticatedUser
):
    """Update a comment"""
    try:
        existing = (
            supabase.table("post_comments")
            .select("author_id")
            .eq("id", str(comment_id))
            .eq("post_id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if existing.data["author_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        supabase.table("post_comments").update({"content": updates.content}).eq(
            "id", str(comment_id)
        ).execute()

        return await get_comment(post_id, comment_id, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment(post_id: UUID, comment_id: UUID, user: AuthenticatedUser):
    """Delete a comment"""
    try:
        existing = (
            supabase.table("post_comments")
            .select("author_id")
            .eq("id", str(comment_id))
            .eq("post_id", str(post_id))
            .single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if existing.data["author_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        replies = (
            supabase.table("post_comments")
            .select("id")
            .eq("parent_id", str(comment_id))
            .limit(1)
            .execute()
        )

        if replies.data:
            supabase.table("post_comments").update({"is_deleted": True}).eq(
                "id", str(comment_id)
            ).execute()
            return {"message": "Comment soft deleted successfully"}
        else:
            supabase.table("post_comments").delete().eq("id", str(comment_id)).execute()

            supabase.rpc("decrement_comment_count", {"post_id": str(post_id)}).execute()

            return {"message": "Comment deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
