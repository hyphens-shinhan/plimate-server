from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.mandatory import (
    GoalSubmissionCreate,
    GoalSubmissionUpdate,
    MandatoryActivitiesForYearResponse,
    MandatoryActivityCreate,
    MandatoryActivityResponse,
    MandatoryActivityType,
    MandatoryGoalResponse,
    MandatorySubmissionLookupResponse,
    MandatorySubmissionResponse,
    SimpleReportSubmissionCreate,
    SimpleReportSubmissionUpdate,
)

router = APIRouter(prefix="/reports/mandatory", tags=["mandatory"])


async def _check_admin(user_id: str) -> None:
    """Verify that the user has ADMIN role."""
    result = supabase.table("users").select("role").eq("id", user_id).single().execute()
    if not result.data or result.data.get("role") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can perform this action",
        )


async def _check_yb_role(user_id: str) -> None:
    """Verify that the user has YB role."""
    result = supabase.table("users").select("role").eq("id", user_id).single().execute()
    if not result.data or result.data.get("role") != "YB":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only YB users can perform this action",
        )


def _build_activity_response(activity: dict) -> MandatoryActivityResponse:
    return MandatoryActivityResponse(
        id=activity["id"],
        title=activity["title"],
        year=activity["year"],
        due_date=activity["due_date"],
        activity_type=activity["activity_type"],
        external_url=activity.get("external_url"),
        created_at=activity["created_at"],
    )


def _build_submission_response(
    submission: dict, activity: dict, goals: list[dict] | None = None
) -> MandatorySubmissionResponse:
    return MandatorySubmissionResponse(
        id=submission["id"],
        activity_id=submission["activity_id"],
        activity=_build_activity_response(activity),
        user_id=submission["user_id"],
        is_submitted=submission["is_submitted"],
        created_at=submission["created_at"],
        submitted_at=submission.get("submitted_at"),
        # GOAL type fields
        goals=(
            [
                MandatoryGoalResponse(
                    id=g["id"],
                    category=g["category"],
                    custom_category=g.get("custom_category"),
                    content=g["content"],
                    plan=g["plan"],
                    outcome=g["outcome"],
                )
                for g in (goals or [])
            ]
            if goals
            else None
        ),
        # SIMPLE_REPORT type fields
        report_title=submission.get("report_title"),
        report_content=submission.get("report_content"),
        activity_date=submission.get("activity_date"),
        location=submission.get("location"),
        image_urls=submission.get("image_urls"),
    )


# ==========================================
# ADMIN ENDPOINTS
# ==========================================


@router.post(
    "/admin/activities",
    response_model=MandatoryActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    activity: MandatoryActivityCreate,
    user: AuthenticatedUser,
):
    """Create a mandatory activity. Only admins can perform this action."""
    await _check_admin(str(user.id))

    # Validate URL_REDIRECT requires external_url
    if (
        activity.activity_type == MandatoryActivityType.URL_REDIRECT
        and not activity.external_url
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="external_url is required for URL_REDIRECT activity type",
        )

    try:
        result = (
            supabase.table("mandatory_activities")
            .insert(
                {
                    "title": activity.title,
                    "year": activity.year,
                    "due_date": activity.due_date.isoformat(),
                    "activity_type": activity.activity_type.value,
                    "external_url": activity.external_url,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create activity",
            )

        return _build_activity_response(result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/admin/activities", response_model=list[MandatoryActivityResponse])
async def list_activities(user: AuthenticatedUser):
    """List all mandatory activities. Only admins can perform this action."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("mandatory_activities")
            .select("*")
            .order("year", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        return [_build_activity_response(a) for a in result.data or []]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get(
    "/admin/activities/{activity_id}",
    response_model=MandatoryActivityResponse,
)
async def get_activity_by_id(activity_id: UUID, user: AuthenticatedUser):
    """Get a mandatory activity by ID. Only admins can perform this action."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        return _build_activity_response(result.data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete(
    "/admin/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_activity(activity_id: UUID, user: AuthenticatedUser):
    """Delete a mandatory activity by ID. Only admins can perform this action."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("mandatory_activities")
            .delete()
            .eq("id", str(activity_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get(
    "/admin/submissions/{activity_id}",
    response_model=list[MandatorySubmissionResponse],
)
async def list_submissions_for_activity(activity_id: UUID, user: AuthenticatedUser):
    """List all submissions for an activity. Only admins can perform this action."""
    await _check_admin(str(user.id))

    try:
        # Get the activity
        activity_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not activity_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        activity = activity_result.data

        # Get all submissions for this activity
        submissions_result = (
            supabase.table("mandatory_submissions")
            .select("*")
            .eq("activity_id", str(activity_id))
            .execute()
        )

        submissions = submissions_result.data or []
        if not submissions:
            return []

        # Get goals if GOAL type
        goals_by_submission: dict[str, list[dict]] = {}
        if activity["activity_type"] == MandatoryActivityType.GOAL.value:
            submission_ids = [s["id"] for s in submissions]
            goals_result = (
                supabase.table("mandatory_goals")
                .select("*")
                .in_("submission_id", submission_ids)
                .execute()
            )

            for goal in goals_result.data or []:
                sid = goal["submission_id"]
                goals_by_submission.setdefault(sid, []).append(goal)

        return [
            _build_submission_response(s, activity, goals_by_submission.get(s["id"]))
            for s in submissions
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


# ==========================================
# USER ENDPOINTS (YB users)
# ==========================================


@router.get("/{year}", response_model=MandatoryActivitiesForYearResponse)
async def get_activities_for_year(year: int, user: AuthenticatedUser):
    """Get all mandatory activities and user's submissions for a given year."""
    await _check_yb_role(str(user.id))

    try:
        # Get all activities for this year
        activities_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("year", year)
            .order("created_at")
            .execute()
        )

        activities = activities_result.data or []
        if not activities:
            return MandatoryActivitiesForYearResponse(year=year, activities=[])

        activity_ids = [a["id"] for a in activities]

        # Get user's submissions for these activities
        submissions_result = (
            supabase.table("mandatory_submissions")
            .select("*")
            .in_("activity_id", activity_ids)
            .eq("user_id", str(user.id))
            .execute()
        )

        submissions_by_activity = {
            s["activity_id"]: s for s in submissions_result.data or []
        }

        # Get goals for GOAL type submissions
        goal_type_submission_ids = [
            s["id"]
            for s in submissions_result.data or []
            if any(
                a["id"] == s["activity_id"]
                and a["activity_type"] == MandatoryActivityType.GOAL.value
                for a in activities
            )
        ]

        goals_by_submission: dict[str, list[dict]] = {}
        if goal_type_submission_ids:
            goals_result = (
                supabase.table("mandatory_goals")
                .select("*")
                .in_("submission_id", goal_type_submission_ids)
                .execute()
            )
            for goal in goals_result.data or []:
                sid = goal["submission_id"]
                goals_by_submission.setdefault(sid, []).append(goal)

        # Build response
        result_activities = []
        for activity in activities:
            submission = submissions_by_activity.get(activity["id"])
            result_activities.append(
                MandatorySubmissionLookupResponse(
                    activity=_build_activity_response(activity),
                    submission=(
                        _build_submission_response(
                            submission,
                            activity,
                            (
                                goals_by_submission.get(submission["id"])
                                if submission
                                else None
                            ),
                        )
                        if submission
                        else None
                    ),
                )
            )

        return MandatoryActivitiesForYearResponse(
            year=year, activities=result_activities
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/activity/{activity_id}", response_model=MandatorySubmissionLookupResponse)
async def get_activity_and_submission(activity_id: UUID, user: AuthenticatedUser):
    """Get a single activity and user's submission."""
    await _check_yb_role(str(user.id))

    try:
        # Get the activity
        activity_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not activity_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        activity = activity_result.data

        # Get user's submission
        submission_result = (
            supabase.table("mandatory_submissions")
            .select("*")
            .eq("activity_id", str(activity_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not submission_result.data:
            return MandatorySubmissionLookupResponse(
                activity=_build_activity_response(activity),
                submission=None,
            )

        submission = submission_result.data[0]

        # Get goals if GOAL type
        goals = None
        if activity["activity_type"] == MandatoryActivityType.GOAL.value:
            goals_result = (
                supabase.table("mandatory_goals")
                .select("*")
                .eq("submission_id", submission["id"])
                .execute()
            )
            goals = goals_result.data or []

        return MandatorySubmissionLookupResponse(
            activity=_build_activity_response(activity),
            submission=_build_submission_response(submission, activity, goals),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/activity/{activity_id}/goal",
    response_model=MandatorySubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_goal_submission(
    activity_id: UUID,
    submission: GoalSubmissionCreate,
    user: AuthenticatedUser,
):
    """Create a submission for a GOAL type activity."""
    await _check_yb_role(str(user.id))

    try:
        # Get the activity and validate type
        activity_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not activity_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        activity = activity_result.data

        if activity["activity_type"] != MandatoryActivityType.GOAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for GOAL type activities",
            )

        # Check if submission already exists
        existing = (
            supabase.table("mandatory_submissions")
            .select("id")
            .eq("activity_id", str(activity_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A submission for this activity already exists",
            )

        # Create submission
        submission_result = (
            supabase.table("mandatory_submissions")
            .insert(
                {
                    "activity_id": str(activity_id),
                    "user_id": str(user.id),
                }
            )
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create submission",
            )

        new_submission = submission_result.data[0]

        # Create goals
        goal_rows = [
            {
                "submission_id": new_submission["id"],
                "category": g.category.value,
                "custom_category": g.custom_category,
                "content": g.content,
                "plan": g.plan,
                "outcome": g.outcome,
            }
            for g in submission.goals
        ]

        goals_result = supabase.table("mandatory_goals").insert(goal_rows).execute()

        return _build_submission_response(
            new_submission, activity, goals_result.data or []
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/activity/{activity_id}/simple-report",
    response_model=MandatorySubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_simple_report_submission(
    activity_id: UUID,
    submission: SimpleReportSubmissionCreate,
    user: AuthenticatedUser,
):
    """Create a submission for a SIMPLE_REPORT type activity."""
    await _check_yb_role(str(user.id))

    try:
        # Get the activity and validate type
        activity_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not activity_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        activity = activity_result.data

        if activity["activity_type"] != MandatoryActivityType.SIMPLE_REPORT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for SIMPLE_REPORT type activities",
            )

        # Check if submission already exists
        existing = (
            supabase.table("mandatory_submissions")
            .select("id")
            .eq("activity_id", str(activity_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A submission for this activity already exists",
            )

        # Create submission with report fields
        submission_result = (
            supabase.table("mandatory_submissions")
            .insert(
                {
                    "activity_id": str(activity_id),
                    "user_id": str(user.id),
                    "report_title": submission.report_title,
                    "report_content": submission.report_content,
                    "activity_date": submission.activity_date.isoformat(),
                    "location": submission.location,
                    "image_urls": submission.image_urls,
                }
            )
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create submission",
            )

        return _build_submission_response(submission_result.data[0], activity)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post(
    "/activity/{activity_id}/url-redirect",
    response_model=MandatorySubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_url_redirect_submission(
    activity_id: UUID,
    user: AuthenticatedUser,
):
    """Create an empty submission for a URL_REDIRECT type activity (to track user started)."""
    await _check_yb_role(str(user.id))

    try:
        # Get the activity and validate type
        activity_result = (
            supabase.table("mandatory_activities")
            .select("*")
            .eq("id", str(activity_id))
            .single()
            .execute()
        )

        if not activity_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

        activity = activity_result.data

        if activity["activity_type"] != MandatoryActivityType.URL_REDIRECT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for URL_REDIRECT type activities",
            )

        # Check if submission already exists
        existing = (
            supabase.table("mandatory_submissions")
            .select("id")
            .eq("activity_id", str(activity_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A submission for this activity already exists",
            )

        # Create empty submission
        submission_result = (
            supabase.table("mandatory_submissions")
            .insert(
                {
                    "activity_id": str(activity_id),
                    "user_id": str(user.id),
                }
            )
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create submission",
            )

        return _build_submission_response(submission_result.data[0], activity)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{submission_id}/goal", response_model=MandatorySubmissionResponse)
async def update_goal_submission(
    submission_id: UUID,
    update: GoalSubmissionUpdate,
    user: AuthenticatedUser,
):
    """Update a draft GOAL submission. Cannot update after submission."""
    await _check_yb_role(str(user.id))

    try:
        # Get submission with activity
        submission_result = (
            supabase.table("mandatory_submissions")
            .select("*, mandatory_activities(*)")
            .eq("id", str(submission_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

        submission = submission_result.data
        activity = submission["mandatory_activities"]

        if activity["activity_type"] != MandatoryActivityType.GOAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for GOAL type submissions",
            )

        if submission["is_submitted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update an already submitted report",
            )

        # Delete existing goals
        supabase.table("mandatory_goals").delete().eq(
            "submission_id", str(submission_id)
        ).execute()

        # Insert new goals
        goal_rows = [
            {
                "submission_id": str(submission_id),
                "category": g.category.value,
                "custom_category": g.custom_category,
                "content": g.content,
                "plan": g.plan,
                "outcome": g.outcome,
            }
            for g in update.goals
        ]

        goals_result = supabase.table("mandatory_goals").insert(goal_rows).execute()

        return _build_submission_response(submission, activity, goals_result.data or [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch(
    "/{submission_id}/simple-report", response_model=MandatorySubmissionResponse
)
async def update_simple_report_submission(
    submission_id: UUID,
    update: SimpleReportSubmissionUpdate,
    user: AuthenticatedUser,
):
    """Update a draft SIMPLE_REPORT submission. Cannot update after submission."""
    await _check_yb_role(str(user.id))

    try:
        # Get submission with activity
        submission_result = (
            supabase.table("mandatory_submissions")
            .select("*, mandatory_activities(*)")
            .eq("id", str(submission_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

        submission = submission_result.data
        activity = submission["mandatory_activities"]

        if activity["activity_type"] != MandatoryActivityType.SIMPLE_REPORT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for SIMPLE_REPORT type submissions",
            )

        if submission["is_submitted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update an already submitted report",
            )

        # Update submission fields
        update_result = (
            supabase.table("mandatory_submissions")
            .update(
                {
                    "report_title": update.report_title,
                    "report_content": update.report_content,
                    "activity_date": update.activity_date.isoformat(),
                    "location": update.location,
                    "image_urls": update.image_urls,
                }
            )
            .eq("id", str(submission_id))
            .execute()
        )

        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update submission",
            )

        return _build_submission_response(update_result.data[0], activity)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{submission_id}/submit", response_model=MandatorySubmissionResponse)
async def submit_submission(submission_id: UUID, user: AuthenticatedUser):
    """Finalize and submit a GOAL or SIMPLE_REPORT submission. Cannot be undone."""
    await _check_yb_role(str(user.id))

    try:
        # Get submission with activity
        submission_result = (
            supabase.table("mandatory_submissions")
            .select("*, mandatory_activities(*)")
            .eq("id", str(submission_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

        submission = submission_result.data
        activity = submission["mandatory_activities"]

        if activity["activity_type"] == MandatoryActivityType.URL_REDIRECT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use /complete endpoint for URL_REDIRECT activities",
            )

        if submission["is_submitted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Submission has already been submitted",
            )

        # Update submission to submitted
        update_result = (
            supabase.table("mandatory_submissions")
            .update(
                {
                    "is_submitted": True,
                    "submitted_at": datetime.now().isoformat(),
                }
            )
            .eq("id", str(submission_id))
            .execute()
        )

        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to submit",
            )

        updated_submission = update_result.data[0]

        # Get goals if GOAL type
        goals = None
        if activity["activity_type"] == MandatoryActivityType.GOAL.value:
            goals_result = (
                supabase.table("mandatory_goals")
                .select("*")
                .eq("submission_id", str(submission_id))
                .execute()
            )
            goals = goals_result.data or []

        return _build_submission_response(updated_submission, activity, goals)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/{submission_id}/complete", response_model=MandatorySubmissionResponse)
async def complete_url_redirect(submission_id: UUID, user: AuthenticatedUser):
    """Mark a URL_REDIRECT submission as complete."""
    await _check_yb_role(str(user.id))

    try:
        # Get submission with activity
        submission_result = (
            supabase.table("mandatory_submissions")
            .select("*, mandatory_activities(*)")
            .eq("id", str(submission_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )

        if not submission_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

        submission = submission_result.data
        activity = submission["mandatory_activities"]

        if activity["activity_type"] != MandatoryActivityType.URL_REDIRECT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This endpoint is only for URL_REDIRECT activities",
            )

        if submission["is_submitted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already marked as complete",
            )

        # Mark as complete
        update_result = (
            supabase.table("mandatory_submissions")
            .update(
                {
                    "is_submitted": True,
                    "submitted_at": datetime.now().isoformat(),
                }
            )
            .eq("id", str(submission_id))
            .execute()
        )

        if not update_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to mark as complete",
            )

        return _build_submission_response(update_result.data[0], activity)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
