from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.club import (
    ClubCategory,
    ClubCreate,
    ClubUpdate,
    UserClubProfile,
    ClubResponse,
    ClubListResponse,
)

router = APIRouter(prefix="/clubs", tags=["clubs"])


def _build_user_profile(row: dict) -> UserClubProfile:
    is_anonymous = bool(row.get("member_nickname"))

    nickname = row.get("member_nickname")
    avatar = row.get("member_avatar_url")

    if not is_anonymous:
        user_data = row.get("users") or {}
        nickname = user_data.get("name")
        avatar = user_data.get("avatar_url")

    return UserClubProfile(
        is_anonymous=is_anonymous,
        nickname=nickname,
        avatar_url=avatar,
    )


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
                    "member_count": 0,
                    "category": club.category,
                    "anonymity": club.anonymity,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        new_club = result.data[0]

        return ClubResponse(
            **new_club, is_member=False, user_profile=None, recent_member_images=None
        )
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

        memberships = (
            supabase.table("club_members")
            .select(
                "club_id, member_nickname, member_avatar_url, users(name, avatar_url)"
            )
            .eq("user_id", str(user.id))
            .in_("club_id", club_ids)
            .execute()
        )

        profiles = {}
        for row in memberships.data:
            profiles[row["club_id"]] = _build_user_profile(row)

        avatars = supabase.rpc("get_club_previews", {"club_ids": club_ids}).execute()

        club_avatars = {}
        for row in avatars.data:
            cid = row["club_id"]
            if cid not in club_avatars:
                club_avatars[cid] = []
            club_avatars[cid].append(row["avatar_url"])

        items = [
            ClubResponse(
                **row,
                is_member=row["id"] in profiles,
                user_profile=profiles.get(row["id"]),
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
            .select("*, users(name, avatar_url)")
            .eq("club_id", str(club_id))
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )
        is_member = bool(membership and membership.data)
        user_profile = None
        if is_member:
            user_profile = _build_user_profile(membership.data)

        return ClubResponse(
            **result.data,
            is_member=is_member,
            user_profile=user_profile,
            recent_member_images=[]
        )
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

        user_data = (
            supabase.table("users")
            .select("name, avatar_url")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
        profile_data = user_data.data if user_data.data else {}

        return ClubResponse(
            **updated.data[0],
            is_member=True,
            user_profile=UserClubProfile(
                is_anonymous=False,
                nickname=profile_data.get("name"),
                avatar_url=profile_data.get("avatar_url"),
            ),
            recent_member_images=[]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{club_id}/join", status_code=status.HTTP_200_OK)
async def join_club(
    club_id: UUID, user_profile: UserClubProfile, user: AuthenticatedUser
):
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

        club_anonymity = (
            supabase.table("clubs")
            .select("anonymity")
            .eq("id", str(club_id))
            .single()
            .execute()
        )
        if not club_anonymity.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Club not found"
            )

        club_anonymity = club_anonymity.data["anonymity"]

        if club_anonymity == "PUBLIC" and user_profile.is_anonymous:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This club requires real profiles.",
            )

        if club_anonymity == "PRIVATE" and not user_profile.is_anonymous:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This club requires anonymous profiles.",
            )

        if user_profile.is_anonymous:
            if not user_profile.nickname:
                raise HTTPException(status_code=400, detail="Nickname required")
            final_nickname = user_profile.nickname
            final_avatar = "random_profile_url"
        else:
            final_nickname = None
            final_avatar = None

        supabase.table("club_members").insert(
            {
                "club_id": str(club_id),
                "user_id": str(user.id),
                "member_nickname": final_nickname,
                "member_avatar_url": final_avatar,
            }
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
