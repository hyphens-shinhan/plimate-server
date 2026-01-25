from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.block import BlockListResponse, BlockedUser

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def block_user(user_id: UUID, user: AuthenticatedUser):
    if str(user_id) == str(user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    existing = (
        supabase.table("blocks")
        .select("blocker_id")
        .eq("blocker_id", str(user.id))
        .eq("blocked_id", str(user_id))
        .execute()
    )

    if existing.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    supabase.table("follows").delete().or_(
        f"and(requester_id.eq.{user.id},receiver_id.eq.{user_id}),"
        f"and(requester_id.eq.{user_id},receiver_id.eq.{user.id})"
    ).execute()

    result = (
        supabase.table("blocks")
        .insert(
            {
                "blocker_id": str(user.id),
                "blocked_id": str(user_id),
            }
        )
        .execute()
    )

    return {"message": "User blocked successfully"}


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def unblock_user(user_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("blocks")
        .delete()
        .eq("blocker_id", str(user.id))
        .eq("blocked_id", str(user_id))
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return {"message": "User unblocked successfully"}


@router.get("", response_model=BlockListResponse)
async def get_blocked_users(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    result = (
        supabase.table("blocks")
        .select(
            "blocked_id, created_at, users!blocks_blocked_id_fkey(id, name, avatar_url)",
            count="exact",
        )
        .eq("blocker_id", str(user.id))
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    users = []
    for row in result.data:
        user_data = row.get("users")
        if user_data:
            users.append(
                BlockedUser(
                    id=user_data["id"],
                    name=user_data["name"],
                    avatar_url=user_data["avatar_url"],
                    blocked_at=row["created_at"],
                )
            )

    return BlockListResponse(users=users, total=result.count or len(users))


@router.get("/{user_id}/status")
async def check_block_status(user_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("blocks")
        .select("blocker_id")
        .eq("blocker_id", str(user.id))
        .eq("blocked_id", str(user_id))
        .execute()
    )

    return {"is_blocked": bool(result.data)}
