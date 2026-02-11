from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.api.v1.grades import calculate_gpa
from app.schemas.grades import SemesterGradeResponse
from app.schemas.user import (
    MandatoryActivityStatus,
    MandatoryStatusResponse,
    ScholarshipEligibilityResponse,
    UserHomeProfile,
    UserMyProfile,
    UserProfileUpdate,
    UserPublicProfile,
    UserPrivacySettings,
    UserPrivacyUpdate,
    VolunteerHoursResponse,
    VolunteerHoursUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserHomeProfile)
async def get_current_user_home_profile(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("users")
            .select(
                "id, name, avatar_url, role, user_profiles(affiliation, major, scholarship_type, scholarship_batch)"
            )
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        data = result.data
        profile = data.pop("user_profiles", {}) or {}

        return UserHomeProfile(
            id=data["id"],
            name=data["name"],
            role=data["role"],
            avatar_url=data.get("avatar_url"),
            affiliation=profile.get("affiliation"),
            major=profile.get("major"),
            scholarship_type=profile.get("scholarship_type"),
            scholarship_batch=profile.get("scholarship_batch"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me/profile", response_model=UserMyProfile)
async def get_current_user_my_profile(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("users_with_email")
            .select("*, user_profiles(*)")
            .eq("id", str(user.id))
            .single()
            .execute()
        )

        data = result.data
        profile = data.pop("user_profiles", {}) or {}

        return UserMyProfile(
            id=data["id"],
            scholar_number=data["scholar_number"],
            name=data["name"],
            email=data["email"],
            role=data["role"],
            avatar_url=data.get("avatar_url"),
            phone_number=profile.get("phone_number"),
            affiliation=profile.get("affiliation"),
            major=profile.get("major"),
            scholarship_type=profile.get("scholarship_type"),
            scholarship_batch=profile.get("scholarship_batch"),
            bio=profile.get("bio"),
            interests=profile.get("interests"),
            hobbies=profile.get("hobbies"),
            address=profile.get("address"),
            volunteer_hours=profile.get("volunteer_hours", 0),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/me/profile", response_model=UserMyProfile)
async def update_current_user_my_profile(
    updates: UserProfileUpdate, user: AuthenticatedUser
):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        if "avatar_url" in update_data:
            avatar_url = update_data.pop("avatar_url")
            supabase.table("users").update({"avatar_url": avatar_url}).eq(
                "id", str(user.id)
            ).execute()

        if update_data:
            update_data["user_id"] = str(user.id)
            supabase.table("user_profiles").upsert(update_data).execute()

        return await get_current_user_my_profile(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me/scholarship-eligibility", response_model=ScholarshipEligibilityResponse)
async def get_scholarship_eligibility(
    user: AuthenticatedUser,
    year: int | None = Query(None, ge=2000, le=2100),
):
    """Get scholarship eligibility summary: GPA, volunteer hours, mandatory progress."""
    current_year = year or datetime.now().year

    # 1. Fetch semester grades for the year
    grades_result = (
        supabase.table("semester_grades")
        .select("*")
        .eq("user_id", str(user.id))
        .eq("year", current_year)
        .execute()
    )

    grades = [SemesterGradeResponse(**row) for row in grades_result.data or []]
    gpa_data = calculate_gpa(grades)

    # 2. Fetch volunteer hours
    profile_result = (
        supabase.table("user_profiles")
        .select("volunteer_hours")
        .eq("user_id", str(user.id))
        .maybe_single()
        .execute()
    )
    volunteer_hours = ((profile_result.data if profile_result else None) or {}).get("volunteer_hours", 0) or 0

    # 3. Fetch mandatory activity progress for the year
    activities_result = (
        supabase.table("mandatory_activities")
        .select("id")
        .eq("year", current_year)
        .execute()
    )
    mandatory_total = len(activities_result.data or [])

    mandatory_completed = 0
    if mandatory_total > 0:
        activity_ids = [a["id"] for a in activities_result.data]
        submissions_result = (
            supabase.table("mandatory_submissions")
            .select("id")
            .eq("user_id", str(user.id))
            .in_("activity_id", activity_ids)
            .eq("is_submitted", True)
            .execute()
        )
        mandatory_completed = len(submissions_result.data or [])

    return ScholarshipEligibilityResponse(
        current_year=current_year,
        gpa=gpa_data["gpa"],
        total_credits=gpa_data["total_credits"],
        semester_breakdown=gpa_data["semester_breakdown"],
        volunteer_hours=volunteer_hours,
        mandatory_total=mandatory_total,
        mandatory_completed=mandatory_completed,
    )


@router.get("/me/mandatory-status", response_model=MandatoryStatusResponse)
async def get_mandatory_status(
    user: AuthenticatedUser,
    year: int | None = Query(None, ge=2000, le=2100),
):
    """Get per-activity mandatory completion status for the scholarship eligibility widget."""
    current_year = year or datetime.now().year

    activities_result = (
        supabase.table("mandatory_activities")
        .select("id, title, due_date, activity_type")
        .eq("year", current_year)
        .order("due_date")
        .execute()
    )

    activities = activities_result.data or []
    if not activities:
        return MandatoryStatusResponse(
            year=current_year, total=0, completed=0, activities=[]
        )

    activity_ids = [a["id"] for a in activities]
    submissions_result = (
        supabase.table("mandatory_submissions")
        .select("activity_id")
        .eq("user_id", str(user.id))
        .in_("activity_id", activity_ids)
        .eq("is_submitted", True)
        .execute()
    )

    completed_ids = {s["activity_id"] for s in submissions_result.data or []}

    activity_statuses = [
        MandatoryActivityStatus(
            id=a["id"],
            title=a["title"],
            due_date=a["due_date"],
            activity_type=a["activity_type"],
            is_completed=a["id"] in completed_ids,
        )
        for a in activities
    ]

    return MandatoryStatusResponse(
        year=current_year,
        total=len(activities),
        completed=len(completed_ids),
        activities=activity_statuses,
    )


@router.get("/me/privacy", response_model=UserPrivacySettings)
async def get_current_user_privacy(user: AuthenticatedUser):
    try:
        result = (
            supabase.table("user_profiles")
            .select(
                "is_location_public, is_contact_public, is_scholarship_public, is_follower_public"
            )
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            return UserPrivacySettings(
                is_location_public=False,
                is_contact_public=False,
                is_scholarship_public=False,
                is_follower_public=False,
            )

        return UserPrivacySettings(**result.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/me/privacy")
async def update_current_user_privacy(
    updates: UserPrivacyUpdate, user: AuthenticatedUser
):
    update_data = updates.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        result = (
            supabase.table("user_profiles")
            .update(update_data)
            .eq("user_id", str(user.id))
            .execute()
        )

        return UserPrivacySettings(**result.data[0])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{user_id}", response_model=UserPublicProfile)
async def get_user_public_profile(user_id: str, user: AuthenticatedUser):
    result = (
        supabase.table("users_with_email")
        .select(
            "id, name, avatar_url, role, email, user_profiles(affiliation, major, scholarship_type, scholarship_batch, bio, interests, hobbies, address, phone_number, is_location_public, is_scholarship_public, is_contact_public)"
        )
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    data = result.data
    profile = data.pop("user_profiles", {}) or {}

    is_location_public = profile["is_location_public"]
    is_contact_public = profile["is_contact_public"]
    is_scholarship_public = profile["is_scholarship_public"]

    # Check follow relationship in both directions
    follow_status = None
    follow_result = (
        supabase.table("follows")
        .select("status")
        .or_(
            f"and(requester_id.eq.{user.id},receiver_id.eq.{user_id}),"
            f"and(requester_id.eq.{user_id},receiver_id.eq.{user.id})"
        )
        .limit(1)
        .execute()
    )
    if follow_result.data:
        follow_status = follow_result.data[0]["status"]

    return UserPublicProfile(
        id=data["id"],
        name=data["name"],
        role=data["role"],
        avatar_url=data.get("avatar_url"),
        email=data["email"] if is_contact_public else None,
        phone_number=profile.get("phone_number") if is_contact_public else None,
        affiliation=profile.get("affiliation"),
        major=profile.get("major"),
        scholarship_type=(
            profile.get("scholarship_type") if is_scholarship_public else None
        ),
        scholarship_batch=(profile.get("scholarship_batch")),
        bio=profile.get("bio"),
        interests=profile.get("interests"),
        hobbies=profile.get("hobbies"),
        address=profile.get("address") if is_location_public else None,
        follow_status=follow_status,
    )


@router.get("/me/volunteer", response_model=VolunteerHoursResponse)
async def get_my_volunteer_hours(user: AuthenticatedUser):
    """Get current user's volunteer hours."""
    try:
        result = (
            supabase.table("user_profiles")
            .select("volunteer_hours")
            .eq("user_id", str(user.id))
            .maybe_single()
            .execute()
        )

        if not result or not result.data:
            return VolunteerHoursResponse(volunteer_hours=0)

        return VolunteerHoursResponse(**result.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/me/volunteer", response_model=VolunteerHoursResponse)
async def update_my_volunteer_hours(
    update: VolunteerHoursUpdate, user: AuthenticatedUser
):
    """Update current user's volunteer hours."""
    try:
        # Upsert into user_profiles
        supabase.table("user_profiles").upsert(
            {
                "user_id": str(user.id),
                "volunteer_hours": update.volunteer_hours,
            }
        ).execute()

        return VolunteerHoursResponse(volunteer_hours=update.volunteer_hours)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
