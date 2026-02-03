from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.academic import (
    AcademicGoalCategory,
    AcademicReportCreate,
    AcademicReportListResponse,
    AcademicReportLookupResponse,
    AcademicReportResponse,
    AcademicReportUpdate,
    GoalResponse,
)

router = APIRouter(prefix="/reports/academic", tags=["academic"])


async def _check_academic_monitoring_for_year(user_id: str, year: int):
    """Verify the user has academic monitoring enabled for the given year."""
    result = (
        supabase.table("academic_monitoring_years")
        .select("year")
        .eq("user_id", user_id)
        .eq("year", year)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Academic monitoring is not enabled for this user in {year}",
        )


async def _get_user_monitoring_years(user_id: str) -> list[int]:
    """Get all years the user is monitored for."""
    result = (
        supabase.table("academic_monitoring_years")
        .select("year")
        .eq("user_id", user_id)
        .order("year", desc=True)
        .execute()
    )
    return [r["year"] for r in result.data or []]


async def _check_admin(user_id: str):
    """Verify the user has ADMIN role."""
    result = supabase.table("users").select("role").eq("id", user_id).single().execute()

    if not result.data or result.data["role"] != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can perform this action",
        )


def _build_report_response(report: dict, goals: list[dict]) -> AcademicReportResponse:
    return AcademicReportResponse(
        id=report["id"],
        user_id=report["user_id"],
        year=report["year"],
        month=report["month"],
        is_submitted=report.get("is_submitted", False),
        created_at=report["created_at"],
        submitted_at=report.get("submitted_at"),
        evidence_urls=report.get("evidence_urls"),
        goals=[
            GoalResponse(
                id=g["id"],
                category=AcademicGoalCategory(g["category"]),
                custom_category=g.get("custom_category"),
                content=g["content"],
                achievement_pct=g["achievement_pct"],
            )
            for g in goals
        ],
    )


@router.post(
    "",
    response_model=AcademicReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_academic_report(
    report: AcademicReportCreate,
    user: AuthenticatedUser,
):
    await _check_academic_monitoring_for_year(str(user.id), report.year)

    try:
        report_result = (
            supabase.table("academic_reports")
            .insert(
                {
                    "user_id": str(user.id),
                    "year": report.year,
                    "month": report.month,
                    "evidence_urls": report.evidence_urls,
                }
            )
            .execute()
        )

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create report",
            )

        new_report = report_result.data[0]
        report_id = new_report["id"]

        goal_rows = [
            {
                "report_id": report_id,
                "category": g.category.value,
                "custom_category": (
                    g.custom_category
                    if g.category == AcademicGoalCategory.OTHER
                    else None
                ),
                "content": g.content,
                "achievement_pct": g.achievement_pct,
            }
            for g in report.goals
        ]

        goals_result = supabase.table("academic_goals").insert(goal_rows).execute()

        return _build_report_response(new_report, goals_result.data or [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("", response_model=AcademicReportListResponse)
async def list_my_reports(
    user: AuthenticatedUser,
    year: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # If year specified, check monitoring for that year; otherwise list all
    monitoring_years = await _get_user_monitoring_years(str(user.id))
    if not monitoring_years:
        return AcademicReportListResponse(reports=[], total=0)

    try:
        query = (
            supabase.table("academic_reports")
            .select("*", count=CountMethod.exact)
            .eq("user_id", str(user.id))
        )

        if year:
            query = query.eq("year", year)

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        reports = []
        for r in result.data or []:
            goals_result = (
                supabase.table("academic_goals")
                .select("*")
                .eq("report_id", r["id"])
                .execute()
            )
            reports.append(_build_report_response(r, goals_result.data or []))

        return AcademicReportListResponse(reports=reports, total=result.count or 0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{year}/{month}", response_model=AcademicReportLookupResponse)
async def get_report_by_year_month(
    year: int,
    month: int,
    user: AuthenticatedUser,
):
    await _check_academic_monitoring_for_year(str(user.id), year)

    try:
        # Look for specific year/month report
        report_result = (
            supabase.table("academic_reports")
            .select("*")
            .eq("user_id", str(user.id))
            .eq("year", year)
            .eq("month", month)
            .execute()
        )

        if not report_result.data:
            return AcademicReportLookupResponse(
                exists=False,
                report=None,
            )

        report = report_result.data[0]
        goals_result = (
            supabase.table("academic_goals")
            .select("*")
            .eq("report_id", report["id"])
            .execute()
        )

        return AcademicReportLookupResponse(
            exists=True,
            report=_build_report_response(report, goals_result.data or []),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{report_id}", response_model=AcademicReportResponse)
async def update_academic_report(
    report_id: UUID,
    update: AcademicReportUpdate,
    user: AuthenticatedUser,
):
    """Update a draft academic report. Cannot edit after final submission."""
    try:
        # Verify report exists and belongs to user
        report_result = (
            supabase.table("academic_reports")
            .select("*")
            .eq("id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not report_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        existing_report = report_result.data[0]

        # Prevent editing submitted reports
        if existing_report.get("is_submitted"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit a submitted report",
            )

        # Check monitoring for the report's year
        report_year = existing_report["year"]
        await _check_academic_monitoring_for_year(str(user.id), report_year)

        # Update evidence_urls on the report
        supabase.table("academic_reports").update(
            {"evidence_urls": update.evidence_urls}
        ).eq("id", str(report_id)).execute()

        # Delete existing goals and insert new ones
        supabase.table("academic_goals").delete().eq(
            "report_id", str(report_id)
        ).execute()

        goal_rows = [
            {
                "report_id": str(report_id),
                "category": g.category.value,
                "custom_category": (
                    g.custom_category
                    if g.category == AcademicGoalCategory.OTHER
                    else None
                ),
                "content": g.content,
                "achievement_pct": g.achievement_pct,
            }
            for g in update.goals
        ]

        goals_result = supabase.table("academic_goals").insert(goal_rows).execute()

        # Fetch updated report
        updated_report = (
            supabase.table("academic_reports")
            .select("*")
            .eq("id", str(report_id))
            .single()
            .execute()
        )

        return _build_report_response(updated_report.data, goals_result.data or [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{report_id}/submit", response_model=AcademicReportResponse)
async def submit_academic_report(
    report_id: UUID,
    user: AuthenticatedUser,
):
    """Finalize and submit an academic report. Cannot be undone."""
    try:
        # Verify report exists and belongs to user
        report_result = (
            supabase.table("academic_reports")
            .select("*")
            .eq("id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not report_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        existing_report = report_result.data[0]

        # Check if already submitted
        if existing_report.get("is_submitted"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report has already been submitted",
            )

        # Check monitoring for the report's year
        report_year = existing_report["year"]
        await _check_academic_monitoring_for_year(str(user.id), report_year)

        # Submit the report
        supabase.table("academic_reports").update(
            {"is_submitted": True, "submitted_at": "now()"}
        ).eq("id", str(report_id)).execute()

        # Fetch updated report
        updated_report = (
            supabase.table("academic_reports")
            .select("*")
            .eq("id", str(report_id))
            .single()
            .execute()
        )

        goals_result = (
            supabase.table("academic_goals")
            .select("*")
            .eq("report_id", str(report_id))
            .execute()
        )

        return _build_report_response(updated_report.data, goals_result.data or [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ── Admin endpoints ──


@router.post("/admin/users/{user_id}/monitoring/{year}", status_code=status.HTTP_201_CREATED)
async def enable_academic_monitoring(
    user_id: UUID, year: int, user: AuthenticatedUser
):
    """Enable academic monitoring for a user for a specific year."""
    await _check_admin(str(user.id))

    try:
        # Check if already exists
        existing = (
            supabase.table("academic_monitoring_years")
            .select("year")
            .eq("user_id", str(user_id))
            .eq("year", year)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Monitoring already enabled for {year}",
            )

        supabase.table("academic_monitoring_years").insert(
            {"user_id": str(user_id), "year": year}
        ).execute()

        return {"user_id": str(user_id), "year": year, "enabled": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/admin/users/{user_id}/monitoring/{year}", status_code=status.HTTP_200_OK)
async def disable_academic_monitoring(
    user_id: UUID, year: int, user: AuthenticatedUser
):
    """Disable academic monitoring for a user for a specific year."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("academic_monitoring_years")
            .delete()
            .eq("user_id", str(user_id))
            .eq("year", year)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Monitoring not enabled for {year}",
            )

        return {"user_id": str(user_id), "year": year, "enabled": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/admin/users/{user_id}/monitoring")
async def get_user_monitoring_years(user_id: UUID, user: AuthenticatedUser):
    """Get all years a user is monitored for."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("academic_monitoring_years")
            .select("year")
            .eq("user_id", str(user_id))
            .order("year", desc=True)
            .execute()
        )

        return {
            "user_id": str(user_id),
            "years": [r["year"] for r in result.data or []],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get(
    "/admin/users/{user_id}",
    response_model=AcademicReportListResponse,
)
async def list_user_reports(
    user_id: UUID,
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("academic_reports")
            .select("*", count=CountMethod.exact)
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        reports = []
        for r in result.data or []:
            goals_result = (
                supabase.table("academic_goals")
                .select("*")
                .eq("report_id", r["id"])
                .execute()
            )
            reports.append(_build_report_response(r, goals_result.data or []))

        return AcademicReportListResponse(reports=reports, total=result.count or 0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
