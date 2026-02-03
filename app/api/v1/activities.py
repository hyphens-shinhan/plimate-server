from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.activity import (
    AcademicReportStatus,
    ActivitiesSummaryResponse,
    CouncilReportStatus,
    MonthlyActivityStatus,
    YearlyActivitySummary,
)

router = APIRouter(prefix="/activities", tags=["activities"])

# April to December (council activity report months)
COUNCIL_REPORT_MONTHS = list(range(4, 13))
# January to December (academic report months)
ACADEMIC_REPORT_MONTHS = list(range(4, 13))
# All months covered (union of both)
ALL_MONTHS = list(range(4, 13))


def _get_year_range(
    council_years: list[int],
    academic_years: list[int],
    monitoring_years: list[int],
) -> tuple[int, int, list[int]]:
    """Get min year, max year, and list of years from first activity to current year."""
    all_years = set(council_years + academic_years + monitoring_years)
    current_year = datetime.now().year

    if not all_years:
        return current_year, current_year, [current_year]

    min_year = min(all_years)
    max_year = current_year
    return min_year, max_year, list(range(min_year, max_year + 1))


@router.get("", response_model=ActivitiesSummaryResponse)
async def get_activities_summary(user: AuthenticatedUser):
    """
    Get dashboard summary of all user activities with unified monthly structure.
    Each month contains both council_report and academic_report status side by side.
    """
    try:
        # Get user's council membership
        council_member = (
            supabase.table("council_members")
            .select("council_id, councils(id, year)")
            .eq("user_id", str(user.id))
            .execute()
        )

        council_ids = []
        council_years = []
        council_id_by_year: dict[int, str] = {}
        if council_member.data:
            for cm in council_member.data:
                if cm.get("councils"):
                    cid = cm["councils"]["id"]
                    cyear = cm["councils"]["year"]
                    council_ids.append(cid)
                    council_years.append(cyear)
                    council_id_by_year[cyear] = cid

        # Get council activity reports
        council_reports_data = []
        if council_ids:
            reports_result = (
                supabase.table("activity_reports")
                .select("council_id, month, title, councils(year)")
                .in_("council_id", council_ids)
                .execute()
            )
            council_reports_data = reports_result.data or []

        # Get academic monitoring years for the user
        monitoring_result = (
            supabase.table("academic_monitoring_years")
            .select("year")
            .eq("user_id", str(user.id))
            .execute()
        )
        monitoring_years = set(r["year"] for r in monitoring_result.data or [])

        # Get academic reports for the user (only count submitted ones as completed)
        academic_result = (
            supabase.table("academic_reports")
            .select("year, month, is_submitted")
            .eq("user_id", str(user.id))
            .execute()
        )
        academic_data = academic_result.data or []
        academic_years = list({r["year"] for r in academic_data})

        # Calculate available years
        min_year, max_year, available_years = _get_year_range(
            council_years, academic_years, list(monitoring_years)
        )

        # Build council reports lookup: {year: {month: title}}
        council_by_year: dict[int, dict[int, str | None]] = {}
        for report in council_reports_data:
            year = report["councils"]["year"] if report.get("councils") else None
            if year:
                if year not in council_by_year:
                    council_by_year[year] = {}
                council_by_year[year][report["month"]] = report.get("title")

        # Build academic reports lookup: {year: set(months)} - only count submitted reports
        academic_by_year: dict[int, set[int]] = {}
        for report in academic_data:
            if not report.get("is_submitted"):
                continue
            year = report["year"]
            if year not in academic_by_year:
                academic_by_year[year] = set()
            academic_by_year[year].add(report["month"])

        # Build unified yearly summaries
        yearly_summaries = []
        for year in available_years:
            council_data = council_by_year.get(year, {})
            academic_completed = academic_by_year.get(year, set())
            is_monitored = year in monitoring_years

            # Build monthly status for all 12 months
            months = []
            for m in ALL_MONTHS:
                council_completed = m in council_data
                academic_done = m in academic_completed

                months.append(
                    MonthlyActivityStatus(
                        month=m,
                        council_report=CouncilReportStatus(
                            title=council_data.get(m),
                            is_completed=council_completed,
                        ),
                        academic_report=AcademicReportStatus(
                            is_completed=academic_done,
                        ),
                    )
                )

            # Check if all council months (Apr-Dec) are completed
            council_all_completed = all(
                m in council_data for m in COUNCIL_REPORT_MONTHS
            )

            # Check if all academic months (Jan-Dec) are completed
            academic_all_completed = len(academic_completed) == len(
                ACADEMIC_REPORT_MONTHS
            )

            yearly_summaries.append(
                YearlyActivitySummary(
                    year=year,
                    council_id=council_id_by_year.get(year),
                    months=months,
                    council_all_completed=council_all_completed,
                    academic_all_completed=academic_all_completed,
                    academic_is_monitored=is_monitored,
                )
            )

        return ActivitiesSummaryResponse(
            min_year=min_year,
            max_year=max_year,
            years=sorted(yearly_summaries, key=lambda x: x.year, reverse=True),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
