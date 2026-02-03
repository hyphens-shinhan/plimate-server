from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.report import (
    ReportCreate,
    ReportResponse,
    ReceiptResponse,
    ReceiptItemResponse,
    AttendanceResponse,
    ConfirmationStatus,
)

router = APIRouter(prefix="/reports", tags=["reports"])


async def _get_council_and_validate_year(council_id: str, year: int) -> int:
    """Get council and validate that the year matches."""
    result = (
        supabase.table("councils")
        .select("year")
        .eq("id", council_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
        )

    council_year = result.data["year"]
    if council_year != year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Year {year} does not match council year {council_year}",
        )

    return council_year


async def _check_council_leader(user_id: str, council_id: str):
    """Verify that the user is the leader of the specified council."""
    try:
        result = (
            supabase.table("councils")
            .select("leader_id")
            .eq("id", council_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Council not found"
            )

        if str(result.data["leader_id"]) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the council leader can perform this action",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify council leader: {str(e)}",
        )


async def _check_council_member(user_id: str, council_id: str):
    """Verify that the user is a member of the specified council."""
    try:
        result = (
            supabase.table("council_members")
            .select("user_id")
            .eq("council_id", council_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only council members can access this report",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify council membership: {str(e)}",
        )


def _build_receipt_responses(
    receipts: list[dict], receipt_items: list[dict]
) -> list[ReceiptResponse]:
    """Build ReceiptResponse list by grouping receipt_items under their parent receipt."""
    items_by_receipt: dict[str, list[dict]] = {}
    for item in receipt_items:
        rid = item["receipt_id"]
        items_by_receipt.setdefault(rid, []).append(item)

    return [
        ReceiptResponse(
            id=r["id"],
            store_name=r["store_name"],
            image_url=r["image_url"],
            created_at=r["created_at"],
            items=[ReceiptItemResponse(**i) for i in items_by_receipt.get(r["id"], [])],
        )
        for r in receipts
    ]


def _build_report_response(
    report: dict,
    year: int,
    receipts: list[dict],
    receipt_items: list[dict],
    attendance: list[dict],
) -> ReportResponse:
    return ReportResponse(
        id=report["id"],
        council_id=report["council_id"],
        year=year,
        month=report["month"],
        title=report["title"],
        activity_date=report["activity_date"],
        location=report["location"],
        content=report.get("content"),
        image_urls=report.get("image_urls"),
        submitted_at=report["submitted_at"],
        receipts=_build_receipt_responses(receipts, receipt_items),
        attendance=[
            AttendanceResponse(
                user_id=a["user_id"],
                status=a["status"],
                confirmation=a["confirmation"],
            )
            for a in attendance
        ],
    )


@router.post(
    "/council/{council_id}/{year}/{month}",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_report(
    council_id: UUID,
    year: int,
    month: int = Path(..., ge=4, le=12),
    *,
    report: ReportCreate,
    user: AuthenticatedUser,
):
    """
    Submit an activity report for a council, year, and month.
    Only the council leader can submit reports.
    Includes receipts with line items and member attendance records.
    """
    await _get_council_and_validate_year(str(council_id), year)
    await _check_council_leader(str(user.id), str(council_id))

    try:
        # Insert activity report
        report_data = {
            "council_id": str(council_id),
            "month": month,
            "title": report.title,
            "activity_date": report.activity_date.isoformat(),
            "location": report.location,
            "content": report.content,
            "image_urls": report.image_urls,
        }

        report_result = supabase.table("activity_reports").insert(report_data).execute()

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create report",
            )

        new_report = report_result.data[0]
        report_id = new_report["id"]

        # Insert receipts and their items
        all_receipts = []
        all_receipt_items = []
        if report.receipts:
            for receipt in report.receipts:
                receipt_result = (
                    supabase.table("receipts")
                    .insert(
                        {
                            "report_id": report_id,
                            "store_name": receipt.store_name,
                            "image_url": receipt.image_url,
                        }
                    )
                    .execute()
                )

                if not receipt_result.data:
                    continue

                new_receipt = receipt_result.data[0]
                all_receipts.append(new_receipt)

                if receipt.items:
                    item_rows = [
                        {
                            "receipt_id": new_receipt["id"],
                            "item_name": item.item_name,
                            "price": item.price,
                        }
                        for item in receipt.items
                    ]

                    items_result = (
                        supabase.table("receipt_items").insert(item_rows).execute()
                    )
                    all_receipt_items.extend(items_result.data or [])

        # Insert attendance records
        attendance_data = []
        if report.attendance:
            attendance_rows = [
                {
                    "report_id": report_id,
                    "user_id": str(a.user_id),
                    "status": a.status.value,
                }
                for a in report.attendance
            ]

            attendance_result = (
                supabase.table("activity_attendance").insert(attendance_rows).execute()
            )
            attendance_data = attendance_result.data or []

        return _build_report_response(
            new_report, year, all_receipts, all_receipt_items, attendance_data
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/council/{council_id}/{year}/{month}", response_model=ReportResponse)
async def get_report(
    council_id: UUID,
    year: int,
    month: int = Path(..., ge=4, le=12),
    *,
    user: AuthenticatedUser,
):
    """
    Get the activity report for a council, year, and month.
    Only council members can view reports.
    """
    await _get_council_and_validate_year(str(council_id), year)
    await _check_council_member(str(user.id), str(council_id))

    try:
        # Fetch report
        report_result = (
            supabase.table("activity_reports")
            .select("*")
            .eq("council_id", str(council_id))
            .eq("month", month)
            .single()
            .execute()
        )

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
            )

        report = report_result.data
        report_id = report["id"]

        # Fetch receipts
        receipts_result = (
            supabase.table("receipts").select("*").eq("report_id", report_id).execute()
        )
        receipts = receipts_result.data or []

        # Fetch receipt items for all receipts
        receipt_items = []
        if receipts:
            receipt_ids = [r["id"] for r in receipts]
            items_result = (
                supabase.table("receipt_items")
                .select("*")
                .in_("receipt_id", receipt_ids)
                .execute()
            )
            receipt_items = items_result.data or []

        # Fetch attendance
        attendance_result = (
            supabase.table("activity_attendance")
            .select("*")
            .eq("report_id", report_id)
            .execute()
        )

        return _build_report_response(
            report, year, receipts, receipt_items, attendance_result.data or []
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch(
    "/council/{report_id}/attendance/confirm",
    response_model=AttendanceResponse,
)
async def confirm_attendance(report_id: UUID, user: AuthenticatedUser):
    """
    Confirm the authenticated user's own attendance for a report.
    Members can only confirm their own attendance record.
    """
    try:
        # Verify attendance record exists for this user
        existing = (
            supabase.table("activity_attendance")
            .select("*")
            .eq("report_id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found",
            )

        # Update confirmation status
        result = (
            supabase.table("activity_attendance")
            .update({"confirmation": ConfirmationStatus.CONFIRMED.value})
            .eq("report_id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to confirm attendance",
            )

        updated = result.data[0]
        return AttendanceResponse(
            user_id=updated["user_id"],
            status=updated["status"],
            confirmation=updated["confirmation"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch(
    "/council/{report_id}/attendance/reject",
    response_model=AttendanceResponse,
)
async def reject_attendance(report_id: UUID, user: AuthenticatedUser):
    """
    Reject the authenticated user's attendance confirmation for a report.
    Resets confirmation status back to PENDING.
    Members can only reject their own attendance record.
    """
    try:
        # Verify attendance record exists for this user
        existing = (
            supabase.table("activity_attendance")
            .select("*")
            .eq("report_id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attendance record not found",
            )

        # Reset confirmation status to PENDING
        result = (
            supabase.table("activity_attendance")
            .update({"confirmation": ConfirmationStatus.PENDING.value})
            .eq("report_id", str(report_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reject attendance",
            )

        updated = result.data[0]
        return AttendanceResponse(
            user_id=updated["user_id"],
            status=updated["status"],
            confirmation=updated["confirmation"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
