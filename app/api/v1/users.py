from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    UserProfileBase,
    UserProfileUpdate,
    UserPublicProfile,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(user: AuthenticatedUser):
    result = (
        supabase.table("users")
        .select("*, user_profiles(university)")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile_data = data.pop("user_profiles", None)

    if profile_data:
        data["university"] = profile_data.pop("university")

    return UserResponse(**data)


@router.patch("/me", response_model=UserResponse)
async def update_current_user(updates: UserUpdate, user: AuthenticatedUser):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    result = (
        supabase.table("users").update(update_data).eq("id", str(user.id)).execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return await get_current_user(user)


@router.get("/me/profile", response_model=UserProfileBase)
async def get_current_user_profile(user: AuthenticatedUser):
    result = (
        supabase.table("user_profiles")
        .select("*")
        .eq("user_id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        return UserProfileBase(user_id=user.id)

    return UserProfileBase(**result.data[0])


@router.patch("/me/profile", response_model=UserProfileBase)
async def update_current_user_profile(
    updates: UserProfileUpdate, user: AuthenticatedUser
):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    update_data["user_id"] = str(user.id)

    try:
        result = supabase.table("user_profiles").upsert(update_data).execute()

        return UserProfileBase(**result.data[0])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_public_profile(user_id: str, user: AuthenticatedUser):
    result = (
        supabase.table("users")
        .select(
            "id, name, avatar_url, role, user_profiles(university, major, scholarship_batch"
        )
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", None)

    return UserPublicProfile(
        id=data["id"],
        name=data["name"],
        avatar_url=data.get("avatar_url"),
        role=data["role"],
        university=profile.get("university"),
        major=profile.get("major"),
        scholarship_batch=profile.get("scholarship_batch"),
    )
