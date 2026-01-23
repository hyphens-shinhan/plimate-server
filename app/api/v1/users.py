from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.user import (
    UserHomeProfile,
    UserProfileUpdate,
    UserPublicProfile,
    UserFullProfile,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserHomeProfile)
async def get_current_user(user: AuthenticatedUser):
    result = (
        supabase.table("users")
        .select(
            "id, name, avatar_url, role, user_profiles(school, major, scholarship_type, scholarship_batch"
        )
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", {}) or {}

    return UserHomeProfile(
        id=data["id"],
        name=data["name"],
        avatar_url=data["avatar_url"],
        role=data["role"],
        school=profile["school"],
        scholarship_type=profile["scholarship_type"],
        scholarship_batch=profile["scholarship_batch"],
        major=profile.get("major"),
    )


@router.get("/me/profile", response_model=UserFullProfile)
async def get_current_user_profile(user: AuthenticatedUser):
    result = (
        supabase.table("users_with_email")
        .select("*, user_profiles(*)")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", {}) or {}

    return UserFullProfile(
        id=data["id"],
        scholar_number=data["scholar_number"],
        name=data["name"],
        avatar_url=data["avatar_url"],
        role=data["role"],
        school=profile["school"],
        scholarship_type=profile["scholarship_type"],
        scholarship_batch=profile["scholarship_batch"],
        birth_date=profile["birth_date"],
        is_location_public=profile["is_location_public"],
        is_scholarship_public=profile["is_scholarship_public"],
        is_contact_public=profile["is_contact_public"],
        is_follower_public=profile["is_follower_public"],
        major=profile.get("major"),
        interests=profile.get("interests"),
        hobbies=profile.get("hobbies"),
        latitude=profile.get("latitude"),
        longitude=profile.get("longitude"),
    )


@router.patch("/me/profile", response_model=UserFullProfile)
async def update_current_user_profile(
    updates: UserProfileUpdate, user: AuthenticatedUser
):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    update_data["user_id"] = str(user.id)

    try:
        supabase.table("user_profiles").upsert(update_data).execute()

        return await get_current_user_profile(user)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_public_profile(user_id: str, user: AuthenticatedUser):
    result = (
        supabase.table("users_with_email")
        .select(
            "id, name, avatar_url, role, email, user_profiles(school, major, scholarship_type, scholarship_batch, interests, hobbies, is_location_public, is_scholarship_public, is_contact_public, is_follower_public)"
        )
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", {}) or {}

    is_scholarship_public = profile["is_scholarship_public"]
    is_contact_public = profile["is_contact_public"]

    return UserPublicProfile(
        id=data["id"],
        name=data["name"],
        avatar_url=data["avatar_url"],
        role=data["role"],
        school=profile["school"],
        email=data["email"] if is_contact_public else None,
        major=profile.get("major"),
        scholarship_type=profile["scholarship_type"] if is_scholarship_public else None,
        scholarship_batch=(
            profile["scholarship_batch"] if is_scholarship_public else None
        ),
        interests=profile.get("interests"),
        hobbies=profile.get("hobbies"),
    )
