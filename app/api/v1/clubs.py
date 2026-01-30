from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.club import (
    ClubCategory,
    ClubCreate,
    ClubUpdate,
    ClubResponse,
    ClubListResponse,
)

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.post("", response_model=ClubResponse, status_code=status.HTTP_201_CREATED)
async def create_club(club: ClubCreate, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("clubs")
            .insert(
                {
                    "creator_id": str(user.id),
                    "name": club.name,
                    "description": club.description,
                    "member_count": 1,
                    "category": club.category,
                    "is_anonymous": club.is_anonymous,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        new_club = result.data[0]

        supabase.table("club_members").insert(
            {"club_id": new_club["id"], "user_id": str(user.id)}
        ).execute()

        return ClubResponse(**new_club, is_member=True, recent_member_images=[])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("", response_model=ClubListResponse)
async def get_clubs(
    user: AuthenticatedUser,
    category: ClubCategory | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        query = supabase.table("clubs").select("*", count=CountMethod.exact)

        if category:
            query = query.contains("category", [category])

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        clubs = result.data
        if not clubs:
            return ClubListResponse(clubs=[], total=0)

        club_ids = [c["id"] for c in clubs]

        my_memberships = (
            supabase.table("club_members")
            .select("club_id")
            .eq("user_id", str(user.id))
            .in_("club_id", club_ids)
            .execute()
        )
        my_club_ids = {row["club_id"] for row in my_memberships.data}

        avatars = (
            supabase.table("club_members")
            .select("club_id, users(avatar_url)")
            .in_("club_id", club_ids)
            .order("joined_at", desc=True)
            .limit(100)
            .execute()
        )

        club_avatars = {}
        for row in avatars.data:
            gid = row["club_id"]
            user_data = row.get("users")
            if user_data and user_data.get("avatar_url"):
                if gid not in club_avatars:
                    club_avatars[gid] = []
                if len(club_avatars[gid]) < 2:
                    club_avatars[gid].append(user_data["avatar_url"])

        items = [
            ClubResponse(
                **row,
                is_member=row["id"] in my_club_ids,
                recent_member_images=club_avatars.get(row["id"], [])
            )
            for row in clubs
        ]

        return ClubListResponse(clubs=items, total=result.count)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{club_id}", response_model=ClubResponse)
async def get_club(club_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("clubs")
            .select("*")
            .eq("id", str(club_id))
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        membership = (
            supabase.table("club_members")
            .select("*")
            .eq("club_id", str(club_id))
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )
        is_member = bool(membership and membership.data)

        return ClubResponse(**result.data, is_member=is_member, recent_member_images=[])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{club_id}", response_model=ClubResponse)
async def update_club(club_id: UUID, club_update: ClubUpdate, user: AuthenticatedUser):
    try:
        existing = (
            supabase.table("clubs")
            .select("creator_id")
            .eq("id", str(club_id))
            .single()
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if str(existing.data["creator_id"]) != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can update the club",
            )

        update_data = club_update.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

        updated = (
            supabase.table("clubs").update(update_data).eq("id", str(club_id)).execute()
        )

        if not updated.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return ClubResponse(**updated.data[0], is_member=True, recent_member_images=[])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{club_id}/join", status_code=status.HTTP_200_OK)
async def join_club(club_id: UUID, user: AuthenticatedUser):
    try:
        existing = (
            supabase.table("club_members")
            .select("*")
            .eq("club_id", str(club_id))
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )

        if existing and existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Already a member"
            )

        supabase.table("club_members").insert(
            {"club_id": str(club_id), "user_id": str(user.id)}
        ).execute()

        supabase.rpc(
            "increment_club_members", {"row_id": str(club_id), "count_delta": 1}
        ).execute()

        return {"message": "Successfully joined the club"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{club_id}/leave", status_code=status.HTTP_200_OK)
async def leave_club(club_id: UUID, user: AuthenticatedUser):
    try:
        existing = (
            supabase.table("club_members")
            .select("*")
            .eq("club_id", str(club_id))
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )

        if not existing or not existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Not a member"
            )

        supabase.table("club_members").delete().eq("club_id", str(club_id)).eq(
            "user_id", str(user.id)
        ).execute()

        supabase.rpc(
            "increment_club_members", {"row_id": str(club_id), "count_delta": -1}
        ).execute()

        return {"message": "Successfully left the club"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
