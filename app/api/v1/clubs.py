from uuid import UUID

from fastapi import APIRouter, HTTPException, status, Query
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.core.nickname import generate_nickname, get_random_avatar, get_avatar_url
from app.schemas.club import (
    ClubCategory,
    ClubCreate,
    ClubUpdate,
    UserClubProfile,
    ClubResponse,
    ClubListResponse,
    GalleryImageCreate,
    GalleryImageResponse,
    GalleryListResponse,
    ClubMember,
    ClubMemberListResponse,
)

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/generate-nickname")
async def generate_club_nickname(user: AuthenticatedUser):
    """
    Generate random fun nickname for club join.
    Call repeatedly for reroll functionality.
    Frontend uses this to let users reroll and pick their preferred anonymous nickname.
    """
    nickname, avatar_id = generate_nickname()
    # Return full URL to frontend, but database will store just the identifier
    return {"nickname": nickname, "avatar_url": get_avatar_url(avatar_id)}


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
        club_id = new_club["id"]

        # Auto-create chat room for the club
        try:
            chat_room = (
                supabase.table("chat_rooms")
                .insert(
                    {
                        "type": "GROUP",
                        "club_id": str(club_id),
                        "name": new_club["name"],
                        "image_url": new_club.get("image_url"),
                        "created_by": str(user.id),
                    }
                )
                .execute()
            )

            # Add creator as chat member
            if chat_room.data:
                supabase.table("chat_room_members").insert(
                    {
                        "room_id": str(chat_room.data[0]["id"]),
                        "user_id": str(user.id),
                    }
                ).execute()
        except Exception as chat_error:
            # Log but don't fail club creation
            # Chat room can be created lazily if this fails
            print(
                f"Warning: Failed to create chat room for club {club_id}: {chat_error}"
            )

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
            query = query.eq("category", category.value)

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
                recent_member_images=club_avatars.get(row["id"], []),
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
            recent_member_images=[],
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
            recent_member_images=[],
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
            # Assign random avatar from anony1-8 pool
            final_avatar = get_random_avatar()
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


@router.post(
    "/{club_id}/gallery",
    response_model=GalleryImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_gallery_image(
    club_id: UUID, image: GalleryImageCreate, user: AuthenticatedUser
):
    try:
        club = (
            supabase.table("clubs")
            .select("creator_id")
            .eq("id", str(club_id))
            .single()
            .execute()
        )

        if not club.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if club.data["creator_id"] != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the club creator can upload gallery images",
            )

        result = (
            supabase.table("club_gallery")
            .insert(
                {
                    "club_id": str(club_id),
                    "image_url": image.image_url,
                    "caption": image.caption,
                    "uploaded_by": str(user.id),
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return GalleryImageResponse(**result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{club_id}/gallery", response_model=GalleryListResponse)
async def get_gallery_images(
    club_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        result = (
            supabase.table("club_gallery")
            .select("*", count=CountMethod.exact)
            .eq("club_id", str(club_id))
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        images = [GalleryImageResponse(**row) for row in (result.data or [])]

        return GalleryListResponse(images=images, total=result.count or len(images))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{club_id}/gallery/{image_id}", status_code=status.HTTP_200_OK)
async def delete_gallery_image(club_id: UUID, image_id: UUID, user: AuthenticatedUser):
    try:
        club = (
            supabase.table("clubs")
            .select("creator_id")
            .eq("id", str(club_id))
            .single()
            .execute()
        )

        if not club.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if club.data["creator_id"] != str(user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        result = (
            supabase.table("club_gallery")
            .delete()
            .eq("id", str(image_id))
            .eq("club_id", str(club_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return {"message": "Gallery image deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{club_id}/members", response_model=ClubMemberListResponse)
async def get_club_members(
    club_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        club = (
            supabase.table("clubs")
            .select("id, anonymity")
            .eq("id", str(club_id))
            .single()
            .execute()
        )

        if not club.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        anonymity = club.data.get("anonymity", "PUBLIC")

        result = (
            supabase.table("club_members")
            .select(
                "user_id, member_nickname, member_avatar_url, "
                "users!club_members_user_id_fkey(id, name, avatar_url)",
                count=CountMethod.exact,
            )
            .eq("club_id", str(club_id))
            .order("joined_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute()
        )

        members = []
        for row in result.data:
            if user_data := row.get("users"):
                use_alias = (
                    anonymity in ("PRIVATE", "BOTH")
                    and row.get("member_nickname")
                )
                members.append(
                    ClubMember(
                        id=user_data["id"],
                        name=row["member_nickname"] if use_alias else user_data["name"],
                        avatar_url=row.get("member_avatar_url") if use_alias else user_data.get("avatar_url"),
                    )
                )

        return ClubMemberListResponse(members=members, total=result.count or 0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
