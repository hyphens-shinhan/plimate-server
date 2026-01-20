from fastapi import APIRouter, HTTPException, status

from app.core import supabase_client
from app.core.deps import AuthenticatedUser
from app.schemas.user import (
    UserResponse,
    UserUpdate,
    UserProfileBase,
    UserProfileUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: AuthenticatedUser):
    result = (
        supabase_client.table("users")
        .select("*, user_profiles(*)")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.patch("/me", response_model=UserResponse)
async def update_current_user(updates: UserUpdate, user: AuthenticatedUser):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    result = (
        supabase_client.table("users")
        .update(update_data)
        .eq("id", str(user.id))
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return await get_current_user_profile(user)


@router.get("/me/profile", response_model=UserProfileBase)
async def get_current_user_profile(user: AuthenticatedUser):
    result = (
        supabase_client.table("user_profiles")
        .select("*")
        .eq("user_id", str(user.id))
        .single()
        .execute()
    )

    if not result.data:
        return UserProfileBase()

    return UserProfileBase(**result.data)


@router.patch("/me/profile", response_model=UserProfileBase)
async def update_current_user_profile(
    updates: UserProfileUpdate, user: AuthenticatedUser
):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    existing = (
        supabase_client.table("user_profiles")
        .select("user_id")
        .eq("user_id", str(user.id))
        .execute()
    )

    if existing.data:
        result = (
            supabase_client.table("user_profiles")
            .update(update_data)
            .eq("user_id", str(user.id))
            .execute()
        )
    else:
        update_data["user_id"] = str(user.id)
        result = supabase_client.table("user_profiles").insert(update_data).execute()

    return UserProfileBase(**result.data[0]) if result.data else UserProfileBase()
