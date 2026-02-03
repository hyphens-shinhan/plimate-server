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

router = APIRouter(prefix="/academic", tags=["academic"])


async def _check_academic_monitoring(user_id: str):
    """Verify the user has academic monitoring enabled."""
    result = (
        supabase.table("user_profiles")
        .select("is_academic_monitoring")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data or not result.data.get("is_academic_monitoring"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Academic monitoring is not enabled for this user",
        )


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
        submitted_at=report["submitted_at"],
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
    await _check_academic_monitoring(str(user.id))

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
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await _check_academic_monitoring(str(user.id))

    try:
        result = (
            supabase.table("academic_reports")
            .select("*", count=CountMethod.exact)
            .eq("user_id", str(user.id))
            .order("submitted_at", desc=True)
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


@router.get("/{report_id}", response_model=AcademicReportResponse)
async def get_academic_report(report_id: UUID, user: AuthenticatedUser):
    await _check_academic_monitoring(str(user.id))

    try:
        report_result = (
            supabase.table("academic_reports")
            .select("*")
            .eq("id", str(report_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        if not report_result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        goals_result = (
            supabase.table("academic_goals")
            .select("*")
            .eq("report_id", str(report_id))
            .execute()
        )

        return _build_report_response(report_result.data, goals_result.data or [])
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
    await _check_academic_monitoring(str(user.id))

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
    await _check_academic_monitoring(str(user.id))

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


# ── Admin endpoints ──


@router.patch("/admin/users/{user_id}/monitoring")
async def toggle_academic_monitoring(user_id: UUID, user: AuthenticatedUser):
    await _check_admin(str(user.id))

    try:
        current = (
            supabase.table("user_profiles")
            .select("is_academic_monitoring")
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )

        if not current.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )

        new_value = not current.data.get("is_academic_monitoring", False)

        supabase.table("user_profiles").update(
            {"is_academic_monitoring": new_value}
        ).eq("user_id", str(user_id)).execute()

        return {"user_id": str(user_id), "is_academic_monitoring": new_value}
    except HTTPException:
        raise
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
            .order("submitted_at", desc=True)
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
