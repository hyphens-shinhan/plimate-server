from uuid import UUID

from fastapi import APIRouter, HTTPException, Body, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.council import (
    CouncilCreate,
    CouncilUpdate,
    CouncilResponse,
    CouncilListResponse,
    CouncilMemberResponse,
    CouncilActivityResponse,
    CouncilActivity,
    MonthActivityStatus,
)

router = APIRouter(prefix="/councils", tags=["councils"])


async def _check_admin(user_id: str):
    try:
        user_data = (
            supabase.table("users").select("role").eq("id", user_id).single().execute()
        )

        if not user_data.data or user_data.data["role"] != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can perform this action",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify admin status: {str(e)}",
        )


@router.post("", response_model=CouncilResponse, status_code=status.HTTP_201_CREATED)
async def create_council(council: CouncilCreate, user: AuthenticatedUser):
    await _check_admin(str(user.id))

    try:
        result = supabase.table("councils").insert(council.model_dump(mode="json")).execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create council",
            )

        new_council = result.data[0]

        return CouncilResponse(**new_council)
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{council_id}", response_model=CouncilResponse)
async def get_council(council_id: UUID, user: AuthenticatedUser):
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("councils")
            .select("*")
            .eq("id", str(council_id))
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
            )

        return CouncilResponse(**result.data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
            )

        return CouncilResponse(**result.data[0])
    except HTTPException:
        raise
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
            )

        return {"message": "Council deleted successfully"}
    except HTTPException:
        raise
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
            )

        target_year = council_result.data["year"]

        existing_membership = (
            supabase.table("council_members")
            .select("council_id, councils!inner(year)")
            .eq("user_id", str(target_user_id))
            .eq("councils.year", target_year)
            .execute()
        )

        if existing_membership.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User is already in a council for year {target_year}",
            )

        supabase.table("council_members").insert(
            {"council_id": str(council_id), "user_id": str(target_user_id)}
        ).execute()

        supabase.rpc(
            "increment_council_members", {"row_id": str(council_id), "count_delta": 1}
        ).execute()

        return {"message": "Member added successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{council_id}/members/{target_user_id}", status_code=status.HTTP_200_OK)
async def remove_council_member(
    council_id: UUID, target_user_id: UUID, user: AuthenticatedUser
):
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("council_members")
            .delete()
            .eq("council_id", str(council_id))
            .eq("user_id", str(target_user_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Council membership not found",
            )

        supabase.rpc(
            "increment_council_members", {"row_id": str(council_id), "count_delta": -1}
        ).execute()

        return {"message": "Member removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get(
    "/{council_id}/members", response_model=list[CouncilMemberResponse]
)
async def get_council_members(council_id: UUID, user: AuthenticatedUser):
    """
    Get all members of a council.
    Only council members can view the member list.
    """
    try:
        # Verify user is a member of this council
        membership = (
            supabase.table("council_members")
            .select("user_id")
            .eq("council_id", str(council_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not membership.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only council members can view the member list",
            )

        # Fetch council to get leader_id
        council_result = (
            supabase.table("councils")
            .select("leader_id")
            .eq("id", str(council_id))
            .single()
            .execute()
        )
        leader_id = council_result.data.get("leader_id") if council_result.data else None

        # Fetch all members with user info
        result = (
            supabase.table("council_members")
            .select("user_id, users!inner(id, name, avatar_url)")
            .eq("council_id", str(council_id))
            .execute()
        )

        members = []
        for row in result.data or []:
            user_data = row.get("users")
            if user_data:
                members.append(CouncilMemberResponse(
                    **user_data,
                    is_leader=(str(user_data["id"]) == str(leader_id)) if leader_id else False,
                ))

        return members
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me/{year}", response_model=CouncilActivityResponse)
async def get_my_council_activity(
    year: int, user: AuthenticatedUser, user_id: UUID | None = Query(None)
):
    """
    Get councils and activity report status for a specific year.
    - Regular users can only view their own councils
    - Admins can view any user's councils by providing user_id query param
    """
    try:
        target_user_id = user_id if user_id else user.id

        # Check authorization: users can only view their own data unless they're admin
        if target_user_id != user.id:
            await _check_admin(str(user.id))

        # Get councils the user was a member of in the specified year
        memberships_result = (
            supabase.table("council_members")
            .select("council_id, councils!inner(*)")
            .eq("user_id", str(target_user_id))
            .eq("councils.year", year)
            .execute()
        )

        if not memberships_result.data:
            return CouncilActivityResponse(year=year, councils=[])

        councils_data = []

        for membership in memberships_result.data:
            council_data = membership.get("councils")
            if not council_data:
                continue

            council_id = council_data["id"]

            # Fetch activity reports for this council
            reports_result = (
                supabase.table("activity_reports")
                .select("id, month, title")
                .eq("council_id", council_id)
                .execute()
            )

            # Build activity status for months 4-12 (April-December)
            activity_status = {}
            reports_by_month = {
                report["month"]: report for report in (reports_result.data or [])
            }

            for month in range(4, 13):
                if month in reports_by_month:
                    report = reports_by_month[month]
                    activity_status[month] = MonthActivityStatus(
                        submitted=True,
                        report_id=report["id"],
                        title=report["title"],
                    )
                else:
                    activity_status[month] = MonthActivityStatus(submitted=False)

            councils_data.append(
                CouncilActivity(
                    id=council_data["id"],
                    year=council_data["year"],
                    affiliation=council_data["affiliation"],
                    region=council_data["region"],
                    leader_id=council_data.get("leader_id"),
                    member_count=council_data.get("member_count", 0),
                    activity_status=activity_status,
                )
            )

        return CouncilActivityResponse(year=year, councils=councils_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
