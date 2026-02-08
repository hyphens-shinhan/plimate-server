from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.core.notifications import create_notification
from app.schemas.notification import NotificationType
from app.schemas.report import (
    ReportUpdate,
    ReportResponse,
    ReceiptResponse,
    ReceiptItemResponse,
    AttendanceResponse,
    ConfirmationStatus,
)

router = APIRouter(prefix="/reports", tags=["councils"])


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
    leader_id: str | None = None,
) -> ReportResponse:
    return ReportResponse(
        id=report["id"],
        council_id=report["council_id"],
        year=year,
        month=report["month"],
        title=report["title"],
        activity_date=report["activity_date"],
        location=report["location"],
        is_submitted=report.get("is_submitted", False),
        is_public=report.get("is_public", False),
        content=report.get("content"),
        image_urls=report.get("image_urls"),
        submitted_at=report["submitted_at"],
        receipts=_build_receipt_responses(receipts, receipt_items),
        attendance=[
            AttendanceResponse(
                user_id=a["user_id"],
                name=(
                    a.get("users", {}).get("name", "Unknown")
                    if a.get("users")
                    else "Unknown"
                ),
                avatar_url=(
                    a.get("users", {}).get("avatar_url") if a.get("users") else None
                ),
                status=a["status"],
                confirmation=a["confirmation"],
                is_leader=(str(a["user_id"]) == str(leader_id)) if leader_id else False,
            )
            for a in attendance
        ],
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
        # Fetch council to get leader_id
        council_result = (
            supabase.table("councils")
            .select("leader_id")
            .eq("id", str(council_id))
            .single()
            .execute()
        )
        leader_id = (
            council_result.data.get("leader_id") if council_result.data else None
        )

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

        # Fetch attendance with user names
        attendance_result = (
            supabase.table("activity_attendance")
            .select("*, users(name, avatar_url)")
            .eq("report_id", report_id)
            .execute()
        )

        return _build_report_response(
            report,
            year,
            receipts,
            receipt_items,
            attendance_result.data or [],
            leader_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/council/{council_id}/{year}/{month}", response_model=ReportResponse)
async def update_report(
    council_id: UUID,
    year: int,
    month: int = Path(..., ge=4, le=12),
    *,
    report_update: ReportUpdate,
    user: AuthenticatedUser,
):
    """
    Create or update a draft activity report for a council, year, and month.
    Only the council leader can create/update reports.
    Cannot update already-submitted reports.
    If the report doesn't exist, it will be created.
    """
    await _get_council_and_validate_year(str(council_id), year)
    await _check_council_leader(str(user.id), str(council_id))

    try:
        # Fetch council to get leader_id
        council_result = (
            supabase.table("councils")
            .select("leader_id")
            .eq("id", str(council_id))
            .single()
            .execute()
        )
        leader_id = (
            council_result.data.get("leader_id") if council_result.data else None
        )

        # Try to fetch existing report
        report_result = (
            supabase.table("activity_reports")
            .select("*")
            .eq("council_id", str(council_id))
            .eq("month", month)
            .execute()
        )

        existing_report = report_result.data[0] if report_result.data else None
        is_new_report = existing_report is None

        if is_new_report:
            # Create new report with provided data
            report_data = {
                "council_id": str(council_id),
                "month": month,
                "title": report_update.title or "",
                "activity_date": (
                    report_update.activity_date.isoformat()
                    if report_update.activity_date
                    else None
                ),
                "location": report_update.location or "",
                "content": report_update.content,
                "image_urls": report_update.image_urls,
            }
            insert_result = (
                supabase.table("activity_reports").insert(report_data).execute()
            )

            if not insert_result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create report",
                )

            updated_report = insert_result.data[0]
            report_id = updated_report["id"]
        else:
            report_id = existing_report["id"]

            # Prevent updates to submitted reports
            if existing_report.get("is_submitted", False):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot update an already-submitted report",
                )

            # Build update data for report fields (only include non-None values)
            update_data = {}
            if report_update.title is not None:
                update_data["title"] = report_update.title
            if report_update.activity_date is not None:
                update_data["activity_date"] = report_update.activity_date.isoformat()
            if report_update.location is not None:
                update_data["location"] = report_update.location
            if report_update.content is not None:
                update_data["content"] = report_update.content
            if report_update.image_urls is not None:
                update_data["image_urls"] = report_update.image_urls

            # Update report if there are changes
            if update_data:
                update_result = (
                    supabase.table("activity_reports")
                    .update(update_data)
                    .eq("id", report_id)
                    .execute()
                )
                updated_report = (
                    update_result.data[0] if update_result.data else existing_report
                )
            else:
                updated_report = existing_report

        # Handle receipts update (replace all if provided)
        all_receipts = []
        all_receipt_items = []
        if report_update.receipts is not None:
            # Delete existing receipts and their items
            existing_receipts = (
                supabase.table("receipts")
                .select("id")
                .eq("report_id", report_id)
                .execute()
            )
            if existing_receipts.data:
                receipt_ids = [r["id"] for r in existing_receipts.data]
                supabase.table("receipt_items").delete().in_(
                    "receipt_id", receipt_ids
                ).execute()
                supabase.table("receipts").delete().eq("report_id", report_id).execute()

            # Insert new receipts
            for receipt in report_update.receipts:
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

                if receipt_result.data:
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
        else:
            # Fetch existing receipts
            receipts_result = (
                supabase.table("receipts")
                .select("*")
                .eq("report_id", report_id)
                .execute()
            )
            all_receipts = receipts_result.data or []
            if all_receipts:
                receipt_ids = [r["id"] for r in all_receipts]
                items_result = (
                    supabase.table("receipt_items")
                    .select("*")
                    .in_("receipt_id", receipt_ids)
                    .execute()
                )
                all_receipt_items = items_result.data or []

        # Handle attendance update (replace all if provided)
        if report_update.attendance is not None:
            # Delete existing attendance
            supabase.table("activity_attendance").delete().eq(
                "report_id", report_id
            ).execute()

            # Insert new attendance - leader is confirmed by default
            if report_update.attendance:
                attendance_rows = [
                    {
                        "report_id": report_id,
                        "user_id": str(a.user_id),
                        "status": a.status.value,
                        "confirmation": (
                            "CONFIRMED"
                            if str(a.user_id) == str(leader_id)
                            else "PENDING"
                        ),
                    }
                    for a in report_update.attendance
                ]
                supabase.table("activity_attendance").insert(attendance_rows).execute()

        # Fetch attendance with user names
        attendance_result = (
            supabase.table("activity_attendance")
            .select("*, users(name, avatar_url)")
            .eq("report_id", report_id)
            .execute()
        )

        return _build_report_response(
            updated_report,
            year,
            all_receipts,
            all_receipt_items,
            attendance_result.data or [],
            leader_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch(
    "/council/{report_id}/confirm",
    response_model=AttendanceResponse,
)
async def confirm_attendance(report_id: UUID, user: AuthenticatedUser):
    """
    Confirm the authenticated user's own attendance for a report.
    Members can only confirm their own attendance record.
    Report must be submitted by the leader first.
    """
    try:
        # Check if report is submitted
        report_result = (
            supabase.table("activity_reports")
            .select("is_submitted")
            .eq("id", str(report_id))
            .single()
            .execute()
        )

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        if not report_result.data.get("is_submitted", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report not yet submitted by leader",
            )

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

        # Fetch user name and avatar
        user_result = (
            supabase.table("users")
            .select("name, avatar_url")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
        user_data = user_result.data or {}

        return AttendanceResponse(
            user_id=updated["user_id"],
            name=user_data.get("name", "Unknown"),
            avatar_url=user_data.get("avatar_url"),
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
    "/council/{report_id}/reject",
    response_model=AttendanceResponse,
)
async def reject_attendance(report_id: UUID, user: AuthenticatedUser):
    """
    Reject the authenticated user's attendance for a report.
    Sets status to ABSENT and confirmation to CONFIRMED (member has responded).
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

        # Mark confirmation as CONFIRMED (member has validated the report)
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
                detail="Failed to reject attendance",
            )

        updated = result.data[0]

        # Fetch user name and avatar
        user_result = (
            supabase.table("users")
            .select("name, avatar_url")
            .eq("id", str(user.id))
            .single()
            .execute()
        )
        user_data = user_result.data or {}

        return AttendanceResponse(
            user_id=updated["user_id"],
            name=user_data.get("name", "Unknown"),
            avatar_url=user_data.get("avatar_url"),
            status=updated["status"],
            confirmation=updated["confirmation"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/council/{report_id}/submit", response_model=ReportResponse)
async def submit_report(report_id: UUID, user: AuthenticatedUser):
    """
    Finalize and submit the report.
    Only the council leader can submit the report.
    """
    try:
        # Get report and council info
        report_result = (
            supabase.table("activity_reports")
            .select("*, councils(id, year, leader_id)")
            .eq("id", str(report_id))
            .single()
            .execute()
        )

        if not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        report = report_result.data
        council = report.get("councils")

        if not council:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Council not found",
            )

        # Check if user is the council leader
        if str(council["leader_id"]) != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the council leader can submit the report",
            )

        # Update is_submitted to true
        update_result = (
            supabase.table("activity_reports")
            .update({"is_submitted": True})
            .eq("id", str(report_id))
            .execute()
        )

        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit report",
            )

        updated_report = update_result.data[0]

        # Fetch receipts
        receipts_result = (
            supabase.table("receipts")
            .select("*")
            .eq("report_id", str(report_id))
            .execute()
        )
        receipts = receipts_result.data or []

        # Fetch receipt items
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

        # Fetch attendance with user names
        attendance_result = (
            supabase.table("activity_attendance")
            .select("*, users(name, avatar_url)")
            .eq("report_id", str(report_id))
            .execute()
        )

        return _build_report_response(
            updated_report,
            council["year"],
            receipts,
            receipt_items,
            attendance_result.data or [],
            council["leader_id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{report_id}/toggle-visibility", response_model=dict)
async def toggle_report_visibility(
    report_id: UUID,
    user: AuthenticatedUser,
):
    """
    Toggle the public visibility of a submitted report.
    Only the council leader can change visibility.
    Report must be submitted before it can be made public.
    When made public, creates a post entry to enable likes/comments/saves.
    """
    try:
        # Get report and council info
        report_result = (
            supabase.table("activity_reports")
            .select("*, councils(id, leader_id)")
            .eq("id", str(report_id))
            .maybe_single()
            .execute()
        )

        if not report_result or not report_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        report = report_result.data
        council = report.get("councils")

        if not council:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Council not found",
            )

        # Check if user is the council leader
        if str(council["leader_id"]) != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the council leader can change report visibility",
            )

        # Report must be submitted before it can be made public
        if not report.get("is_submitted", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report must be submitted before it can be made public",
            )

        # Toggle is_public
        new_is_public = not report.get("is_public", False)
        update_result = (
            supabase.table("activity_reports")
            .update({"is_public": new_is_public})
            .eq("id", str(report_id))
            .execute()
        )

        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update report visibility",
            )

        # Create or delete post entry based on visibility
        if new_is_public:
            # Create a post entry for the council report
            post_result = (
                supabase.table("posts")
                .insert(
                    {
                        "author_id": str(council["leader_id"]),
                        "type": "COUNCIL_REPORT",
                        "title": report.get("title"),
                        "content": report.get("content"),
                        "image_urls": report.get("image_urls"),
                        "report_id": str(report_id),
                    }
                )
                .execute()
            )

            if not post_result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create post for council report",
                )

            # Send notifications to all council members
            council_id = council["id"]
            members_result = (
                supabase.table("council_members")
                .select("user_id")
                .eq("council_id", str(council_id))
                .execute()
            )
            for member in members_result.data or []:
                create_notification(
                    recipient_id=member["user_id"],
                    notification_type=NotificationType.REPORT_EXPORT,
                    message=f"Activity report '{report['title']}' has been shared",
                    actor_id=user.id,
                )
        else:
            # Delete the corresponding post when making private
            supabase.table("posts").delete().eq("report_id", str(report_id)).execute()

        return {
            "is_public": new_is_public,
            "message": f"Report visibility set to {'public' if new_is_public else 'private'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
