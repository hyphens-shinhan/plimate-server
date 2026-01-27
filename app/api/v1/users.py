from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.user import (
    UserHomeProfile,
    UserMyProfile,
    UserProfileUpdate,
    UserPublicProfile,
    UserPrivacySettings,
    UserPrivacyUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserHomeProfile)
async def get_my_home_profile(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("users")
            .select(
                "id, name, avatar_url, role, user_profiles(affiliation, major, scholarship_type, scholarship_batch)"
            )
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        data = result.data
        profile = data.pop("user_profiles", {}) or {}

        return UserHomeProfile(
            id=data["id"],
            name=data["name"],
            role=data["role"],
            avatar_url=data.get("avatar_url"),
            affiliation=profile.get("affiliation"),
            major=profile.get("major"),
            scholarship_type=profile.get("scholarship_type"),
            scholarship_batch=profile.get("scholarship_batch"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me/profile", response_model=UserMyProfile)
async def get_my_profile(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("users_with_email")
            .select("*, user_profiles(*)")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        data = result.data
        profile = data.pop("user_profiles", {}) or {}

        return UserMyProfile(
            id=data["id"],
            scholar_number=data["scholar_number"],
            name=data["name"],
            email=data["email"],
            role=data["role"],
            avatar_url=data.get("avatar_url"),
            affiliation=profile.get("affiliation"),
            major=profile.get("major"),
            scholarship_type=profile.get("scholarship_type"),
            scholarship_batch=profile.get("scholarship_batch"),
            bio=profile.get("bio"),
            interests=profile.get("interests"),
            hobbies=profile.get("hobbies"),
            location=profile.get("location"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/me/profile", response_model=UserMyProfile)
async def update_my_profile(updates: UserProfileUpdate, user: AuthenticatedUser):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        if "avatar_url" in update_data:
            avatar_url = update_data.pop("avatar_url")
            supabase.table("users").update({"avatar_url": avatar_url}).eq(
                "id", str(user.id)
            ).execute()

        if update_data:
            update_data["user_id"] = str(user.id)
            supabase.table("user_profiles").upsert(update_data).execute()

        return await get_my_profile(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me/privacy", response_model=UserPrivacySettings)
async def get_current_user_privacy(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("user_profiles")
            .select(
                "is_location_public, is_contact_public, is_scholarship_public, is_follower_public"
            )
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        return UserPrivacySettings(**result.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/me/privacy")
async def update_user_privacy(updates: UserPrivacyUpdate, user: AuthenticatedUser):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        result = (
            supabase.table("user_profiles")
            .update(update_data)
            .eq("user_id", str(user.id))
            .execute()
        )

        return UserPrivacySettings(**result.data[0])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_public_profile(user_id: str, user: AuthenticatedUser):
    result = (
        supabase.table("users_with_email")
        .select(
            "id, name, avatar_url, role, email, user_profiles(affiliation, major, scholarship_type, scholarship_batch, bio, interests, hobbies, location, is_location_public, is_scholarship_public, is_contact_public)"
        )
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", {}) or {}

    is_location_public = profile["is_location_public"]
    is_contact_public = profile["is_contact_public"]
    is_scholarship_public = profile["is_scholarship_public"]

    return UserPublicProfile(
        id=data["id"],
        name=data["name"],
        role=data["role"],
        avatar_url=data.get("avatar_url"),
        email=data["email"] if is_contact_public else None,
        affiliation=profile.get("affiliation"),
        major=profile.get("major"),
        scholarship_type=(
            profile.get("scholarship_type") if is_scholarship_public else None
        ),
        scholarship_batch=(profile.get("scholarship_batch")),
        bio=profile.get("bio"),
        interests=profile.get("interests"),
        hobbies=profile.get("hobbies"),
        location=profile.get("location") if is_location_public else None,
    )
