from uuid import UUID

from fastapi import APIRouter, status, HTTPException, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.follow import (
    FollowStatusResponse,
    FollowUser,
    FollowListResponse,
    FollowRequestListResponse,
    FollowRequest,
)

router = APIRouter(prefix="/follows", tags=["follows"])


def check_block_exists(user_id_1: str, user_id_2: str) -> bool:
    result = (
        supabase.table("blocks")
        .select("blocker_id")
        .or_(
            f"and(blocker_id.eq.{user_id_1},blocked_id.eq.{user_id_2}),"
            f"and(blocker_id.eq.{user_id_2},blocked_id.eq.{user_id_1})"
        )
        .execute()
    )

    return bool(result.data)


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def send_follow_request(user_id: UUID, user: AuthenticatedUser):
    if str(user_id) == str(user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself"
        )

    if check_block_exists(str(user.id), str(user_id)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    existing = (
        supabase.table("follows")
        .select("id, status")
        .or_(
            f"and(requester_id.eq.{user.id},receiver_id.eq.{user_id}),"
            f"and(requester_id.eq.{user_id},receiver_id.eq.{user.id})"
        )
        .execute()
    )

    if existing.data:
        follow = existing.data[0]
        if follow["status"] == "ACCEPTED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT)
        elif follow["status"] == "PENDING":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    result = (
        supabase.table("follows")
        .insert(
            {
                "requester_id": str(user.id),
                "receiver_id": str(user_id),
                "status": "PENDING",
            }
        )
        .execute()
    )

    return {"message": "Successfully followed user"}


@router.get("/requests", response_model=FollowRequestListResponse)
async def get_pending_requests(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    result = (
        supabase.table("follows")
        .select(
            "id, requester_id, created_at, users!follows_requester_id_fkey(id, name, avatar_url)",
            count=CountMethod.exact,
        )
        .eq("receiver_id", str(user.id))
        .eq("status", "PENDING")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    requests = []
    for row in result.data:
        user_data = row.get("users")
        if user_data:
            requests.append(
                FollowRequest(
                    id=row["id"],
                    requester=FollowUser(**user_data),
                    created_at=row["created_at"],
                )
            )

    return FollowRequestListResponse(
        requests=requests, total=result.count or len(requests)
    )


@router.post("/requests/{request_id}/accept", status_code=status.HTTP_200_OK)
async def accept_follow_request(request_id: UUID, user: AuthenticatedUser):
    existing = (
        supabase.table("follows")
        .select("id, receiver_id, status")
        .eq("id", str(request_id))
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if existing.data["receiver_id"] != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if existing.data["status"] != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    result = (
        supabase.table("follows")
        .update({"status": "ACCEPTED", "accepted_at": "now()"})
        .eq("id", str(request_id))
    ).execute()

    return {"message": "Follow request accepted"}


@router.post("/requests/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_follow_request(request_id: UUID, user: AuthenticatedUser):
    existing = (
        supabase.table("follows")
        .select("id, receiver_id, status")
        .eq("id", str(request_id))
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if existing.data["receiver_id"] != str(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    if existing.data["status"] != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    result = (
        supabase.table("follows")
        .update({"status": "REJECTED"})
        .eq("id", str(request_id))
        .execute()
    )

    return {"message": "Follow request rejected"}


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def unfollow_user(user_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("follows")
        .delete()
        .eq("status", "ACCEPTED")
        .or_(
            f"and(requester_id.eq.{user.id},receiver_id.eq.{user_id}),"
            f"and(requester_id.eq.{user_id},receiver_id.eq.{user.id})"
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return {"message": "Unfollowed successfully"}


@router.get("/{user_id}/status", response_model=FollowStatusResponse)
async def check_follow_status(user_id: UUID, user: AuthenticatedUser):
    result = (
        supabase.table("follows")
        .select("status")
        .or_(
            f"and(requester_id.eq.{user.id},receiver_id.eq.{user_id}),"
            f"and(requester_id.eq.{user_id},receiver_id.eq.{user.id})"
        )
        .execute()
    )

    if not result.data:
        return FollowStatusResponse(status=None, is_following=False)

    follow_status = result.data[0]["status"]
    return FollowStatusResponse(
        status=follow_status, is_following=(follow_status == "ACCEPTED")
    )


@router.get("/me", response_model=FollowListResponse)
async def get_my_followers(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    result1 = (
        supabase.table("follows")
        .select("receiver_id, users!follows_receiver_id_fkey(id, name, avatar_url)")
        .eq("requester_id", str(user.id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    result2 = (
        supabase.table("follows")
        .select("requester_id, users!follows_requester_id_fkey(id, name, avatar_url)")
        .eq("receiver_id", str(user.id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    followers = []
    for row in result1.data:
        user_data = row.get("users")
        if user_data:
            followers.append(FollowUser(**user_data))

    for row in result2.data:
        user_data = row.get("users")
        if user_data:
            followers.append(FollowUser(**user_data))

    total = len(followers)
    followers = followers[offset : offset + limit]

    return FollowListResponse(followers=followers, total=total)


@router.get("/{user_id}", response_model=FollowListResponse)
async def get_user_followers(
    user_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    profile_result = (
        supabase.table("user_profiles")
        .select("is_follower_public")
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )

    is_public = (
        profile_result.data.get("is_follower_public", False)
        if profile_result.data
        else False
    )

    if str(user_id) != str(user.id) and not is_public:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    result1 = (
        supabase.table("follows")
        .select("receiver_id, users!follows_receiver_id_fkey(id, name, avatar_url)")
        .eq("requester_id", str(user_id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    result2 = (
        supabase.table("follows")
        .select("requester_id, users!follows_requester_id_fkey(id, name, avatar_url)")
        .eq("receiver_id", str(user_id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    followers = []
    for row in result1.data:
        user_data = row.get("users")
        if user_data:
            followers.append(FollowUser(**user_data))

    for row in result2.data:
        user_data = row.get("users")
        if user_data:
            followers.append(FollowUser(**user_data))

    total = len(followers)
    followers = followers[offset : offset + limit]

    return FollowListResponse(followers=followers, total=total)
