from uuid import UUID

from fastapi import APIRouter, HTTPException, Body, status
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.council import (
    CouncilCreate,
    CouncilUpdate,
    CouncilResponse,
    CouncilListResponse,
)

router = APIRouter(prefix="/councils", tags=["councils"])


async def _check_admin(user_id: str):
    user_data = (
        supabase.table("users").select("role").eq("id", user_id).single().execute()
    )

    if not user_data.data or user_data.data["role"] != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can perform this action",
        )


@router.post("", response_model=CouncilResponse, status_code=status.HTTP_201_CREATED)
async def create_council(council: CouncilCreate, user: AuthenticatedUser):
    await _check_admin(str(user.id))

    try:
        result = supabase.table("councils").insert(council.model_dump()).execute()

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        new_council = result.data[0]

        return CouncilResponse(**new_council)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{council_id}", response_model=CouncilResponse)
async def update_council(
    council_id: UUID, council_update: CouncilUpdate, user: AuthenticatedUser
):
    await _check_admin(str(user.id))

    try:
        update_data = council_update.model_dump(exclude_unset=True, mode="json")

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
            )

        result = (
            supabase.table("councils")
            .update(update_data)
            .eq("id", str(council_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return CouncilResponse(**result.data[0])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{council_id}", status_code=status.HTTP_200_OK)
async def delete_council(council_id: UUID, user: AuthenticatedUser):
    await _check_admin(str(user.id))

    try:
        result = supabase.table("councils").delete().eq("id", str(council_id)).execute()
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return {"message": "Council deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("", response_model=CouncilListResponse)
async def get_councils(
    user: AuthenticatedUser, year: int | None = None, region: str | None = None
):
    await _check_admin(str(user.id))

    try:
        query = supabase.table("councils").select("*")

        if year:
            query = query.eq("year", year)
        if region:
            query = query.eq("region", region)

        result = query.order("year", desc=True).execute()

        councils = result.data or []

        return CouncilListResponse(
            councils=[CouncilResponse(**row) for row in councils], total=len(councils)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{council_id}", response_model=CouncilResponse)
async def get_council(council_id: UUID, user: AuthenticatedUser):
    try:
        result = (
            supabase.table("councils")
            .select("*")
            .eq("id", str(council_id))
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return CouncilResponse(**result.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{council_id}/members", status_code=status.HTTP_201_CREATED)
async def add_council_member(
    council_id: UUID,
    user: AuthenticatedUser,
    target_user_id: UUID = Body(..., embed=True),
):
    await _check_admin(str(user.id))

    try:
        council_result = (
            supabase.table("councils")
            .select("year")
            .eq("id", str(council_id))
            .single()
            .execute()
        )

        if not council_result.data:
            raise HTTPException(status_code=404, detail="Council not found")

        target_year = council_result.data["year"]

        existing_memberships = (
            supabase.table("council_members")
            .select("council_id, councils!inner(year)")
            .eq("user_id", str(target_user_id))
            .execute()
        )

        for row in existing_memberships.data:
            c_data = row.get("councils")
            if c_data and c_data.get("year") == target_year:
                raise HTTPException(
                    status_code=400,
                    detail=f"User is already in a council for year {target_year}",
                )

        supabase.table("council_members").insert(
            {"council_id": str(council_id), "user_id": str(target_user_id)}
        ).execute()

        supabase.rpc(
            "increment_council_members", {"row_id": str(council_id), "count_delta": 1}
        ).execute()

        return {"message": "Member added successfully"}
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{council_id}/members/{target_user_id}", status_code=status.HTTP_200_OK)
async def remove_council_member(
    council_id: UUID, target_user_id: UUID, user: AuthenticatedUser
):
    await _check_admin(str(user.id))

    try:
        supabase.table("council_members").delete().eq("council_id", str(council_id)).eq(
            "user_id", str(target_user_id)
        ).execute()

        supabase.rpc(
            "increment_council_members", {"row_id": str(council_id), "count_delta": -1}
        ).execute()

        return {"message": "Member removed successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
