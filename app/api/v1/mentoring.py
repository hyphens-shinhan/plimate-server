from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.core.notifications import create_notification
from app.schemas.mentoring import (
    MatchScoreBreakdown,
    MentorMatchingSurveyCreate,
    MentorMatchingSurveyResponse,
    MentorProfileResponse,
    MentorProfileUpdate,
    MentorRecommendationCard,
    MentorRecommendationsResponse,
    MentorSearchCard,
    MentorSearchResponse,
    MentoringRequestCreate,
    MentoringRequestListResponse,
    MentoringRequestResponse,
    RequestUserInfo,
)
from app.schemas.notification import NotificationType

router = APIRouter(prefix="/mentoring", tags=["mentoring"])

# Weights for each matching dimension (availability excluded — hard constraint)
_WEIGHTS = {
    "fields": 0.35,
    "frequency": 0.15,
    "methods": 0.15,
    "communication_styles": 0.20,
    "mentoring_focuses": 0.15,
}

_MIN_MATCH_SCORE = 0.3

# New mentor boost: mentors with fewer active mentees get a score bonus
_NEW_MENTOR_BOOST = 0.10  # max 10% boost
_MENTEE_CAP = 5  # at this many active mentees, boost = 0


def _compute_match_score(
    mentee: dict, mentor: dict
) -> tuple[float, MatchScoreBreakdown] | None:
    """Compute weighted match score between a mentee survey and a mentor profile.

    Returns (total_score, breakdown) where total_score is 0.0-1.0,
    or None if the mentor fails the availability hard constraint.
    """
    # Hard constraint — Available days: must have at least one overlap
    mentee_days = set(mentee["available_days"] or [])
    mentor_days = set(mentor.get("available_days") or [])
    if mentee_days and not (mentee_days & mentor_days):
        return None

    # Hard constraint — Time slots: must have at least one overlap
    mentee_slots = set(mentee["time_slots"] or [])
    mentor_slots = set(mentor.get("time_slots") or [])
    if mentee_slots and not (mentee_slots & mentor_slots):
        return None

    # Availability scores (kept in breakdown for display, not in weighted total)
    days_score = (
        len(mentee_days & mentor_days) / len(mentee_days) if mentee_days else 0.0
    )
    slots_score = (
        len(mentee_slots & mentor_slots) / len(mentee_slots) if mentee_slots else 0.0
    )
    # Step 1 — Fields: mentee-coverage ratio
    # Measures how many of the mentee's desired fields the mentor covers.
    # A mentor with extra fields is not penalized (unlike Jaccard).
    mentee_fields = set(mentee["fields"] or [])
    mentor_fields = set(mentor.get("fields") or [])
    fields_score = (
        len(mentee_fields & mentor_fields) / len(mentee_fields) if mentee_fields else 0.0
    )

    # Frequency: mentee single value IN mentor's accepted list
    mentor_freq = set(mentor.get("frequency") or [])
    frequency_score = 1.0 if mentee["frequency"] in mentor_freq else 0.0

    # Methods: FLEXIBLE acts as wildcard, binary overlap
    mentee_methods = set(mentee["methods"] or [])
    mentor_methods = set(mentor.get("methods") or [])
    if "FLEXIBLE" in mentee_methods or "FLEXIBLE" in mentor_methods:
        methods_score = 1.0
    else:
        methods_score = 1.0 if mentee_methods & mentor_methods else 0.0

    # Communication styles: mentee-coverage ratio
    mentee_styles = set(mentee["communication_styles"] or [])
    mentor_styles = set(mentor.get("communication_styles") or [])
    styles_score = (
        len(mentee_styles & mentor_styles) / len(mentee_styles)
        if mentee_styles
        else 0.0
    )

    # Mentoring focuses: mentee-coverage ratio
    mentee_focuses = set(mentee["mentoring_focuses"] or [])
    mentor_focuses = set(mentor.get("mentoring_focuses") or [])
    focuses_score = (
        len(mentee_focuses & mentor_focuses) / len(mentee_focuses)
        if mentee_focuses
        else 0.0
    )

    scores = {
        "fields": round(fields_score, 4),
        "frequency": round(frequency_score, 4),
        "available_days": round(days_score, 4),
        "time_slots": round(slots_score, 4),
        "methods": round(methods_score, 4),
        "communication_styles": round(styles_score, 4),
        "mentoring_focuses": round(focuses_score, 4),
    }

    total = round(
        sum(_WEIGHTS[k] * scores[k] for k in _WEIGHTS),
        4,
    )

    return total, MatchScoreBreakdown(**scores)


# ==================================================================
# Survey CRUD
# ==================================================================


@router.post(
    "/survey",
    response_model=MentorMatchingSurveyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_survey(
    survey: MentorMatchingSurveyCreate,
    user: AuthenticatedUser,
):
    """Submit a completed 7-step mentor matching survey."""
    result = (
        supabase.table("mentor_matching_surveys")
        .insert(
            {
                "user_id": str(user.id),
                "fields": [f.value for f in survey.fields],
                "frequency": survey.frequency.value,
                "goal": survey.goal,
                "available_days": [d.value for d in survey.available_days],
                "time_slots": [t.value for t in survey.time_slots],
                "methods": [m.value for m in survey.methods],
                "communication_styles": [s.value for s in survey.communication_styles],
                "mentoring_focuses": [f.value for f in survey.mentoring_focuses],
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save survey",
        )

    return result.data[0]


@router.get("/survey/me", response_model=MentorMatchingSurveyResponse)
async def get_my_survey(user: AuthenticatedUser):
    """Get the current user's latest mentor matching survey."""
    result = (
        supabase.table("mentor_matching_surveys")
        .select("*")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No survey found. Please complete the mentor matching survey first.",
        )

    return result.data[0]


@router.put("/survey/me", response_model=MentorMatchingSurveyResponse)
async def update_my_survey(
    survey: MentorMatchingSurveyCreate,
    user: AuthenticatedUser,
):
    """Overwrite the current user's survey (retake). Creates a new record."""
    result = (
        supabase.table("mentor_matching_surveys")
        .insert(
            {
                "user_id": str(user.id),
                "fields": [f.value for f in survey.fields],
                "frequency": survey.frequency.value,
                "goal": survey.goal,
                "available_days": [d.value for d in survey.available_days],
                "time_slots": [t.value for t in survey.time_slots],
                "methods": [m.value for m in survey.methods],
                "communication_styles": [s.value for s in survey.communication_styles],
                "mentoring_focuses": [f.value for f in survey.mentoring_focuses],
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save survey",
        )

    return result.data[0]


# ==================================================================
# Mentor Profile Management
# ==================================================================


@router.patch("/profile", response_model=MentorProfileResponse)
async def update_mentor_profile(
    profile: MentorProfileUpdate,
    user: AuthenticatedUser,
):
    """Update the current mentor's matching profile fields."""
    # Verify user is a mentor
    user_result = (
        supabase.table("users")
        .select("id, name, avatar_url, role")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    if not user_result.data or user_result.data["role"] != "MENTOR":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only mentors can update a mentor profile.",
        )

    # Build update payload (only non-None fields)
    update_data: dict = {}
    if profile.introduction is not None:
        update_data["introduction"] = profile.introduction
    if profile.affiliation is not None:
        update_data["affiliation"] = profile.affiliation
    if profile.expertise is not None:
        update_data["expertise"] = profile.expertise
    if profile.fields is not None:
        update_data["fields"] = [f.value for f in profile.fields]
    if profile.frequency is not None:
        update_data["frequency"] = [f.value for f in profile.frequency]
    if profile.available_days is not None:
        update_data["available_days"] = [d.value for d in profile.available_days]
    if profile.time_slots is not None:
        update_data["time_slots"] = [t.value for t in profile.time_slots]
    if profile.methods is not None:
        update_data["methods"] = [m.value for m in profile.methods]
    if profile.communication_styles is not None:
        update_data["communication_styles"] = [
            s.value for s in profile.communication_styles
        ]
    if profile.mentoring_focuses is not None:
        update_data["mentoring_focuses"] = [
            f.value for f in profile.mentoring_focuses
        ]

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    # Upsert: insert if not exists, update if exists
    upsert_data = {"user_id": str(user.id), **update_data}
    result = (
        supabase.table("mentor_details")
        .upsert(upsert_data, on_conflict="user_id")
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update mentor profile.",
        )

    row = result.data[0]
    return MentorProfileResponse(
        user_id=row["user_id"],
        name=user_result.data["name"],
        avatar_url=user_result.data.get("avatar_url"),
        introduction=row.get("introduction"),
        affiliation=row.get("affiliation"),
        expertise=row.get("expertise"),
        fields=row.get("fields"),
        frequency=row.get("frequency"),
        available_days=row.get("available_days"),
        time_slots=row.get("time_slots"),
        methods=row.get("methods"),
        communication_styles=row.get("communication_styles"),
        mentoring_focuses=row.get("mentoring_focuses"),
    )


@router.get("/profile/me", response_model=MentorProfileResponse)
async def get_my_mentor_profile(user: AuthenticatedUser):
    """Get the current mentor's profile."""
    user_result = (
        supabase.table("users")
        .select("id, name, avatar_url, role")
        .eq("id", str(user.id))
        .maybe_single()
        .execute()
    )

    user_data = (user_result.data if user_result else None) or {}
    if not user_data or user_data.get("role") != "MENTOR":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only mentors can view their mentor profile.",
        )

    details_result = (
        supabase.table("mentor_details")
        .select("*")
        .eq("user_id", str(user.id))
        .maybe_single()
        .execute()
    )

    row = (details_result.data if details_result else None) or {}
    return MentorProfileResponse(
        user_id=user.id,
        name=user_data["name"],
        avatar_url=user_data.get("avatar_url"),
        introduction=row.get("introduction"),
        affiliation=row.get("affiliation"),
        expertise=row.get("expertise"),
        fields=row.get("fields"),
        frequency=row.get("frequency"),
        available_days=row.get("available_days"),
        time_slots=row.get("time_slots"),
        methods=row.get("methods"),
        communication_styles=row.get("communication_styles"),
        mentoring_focuses=row.get("mentoring_focuses"),
    )


# ==================================================================
# Mentor Search & Browse
# ==================================================================


@router.get("/mentors", response_model=MentorSearchResponse)
async def search_mentors(
    user: AuthenticatedUser,
    field: str | None = Query(None, description="Filter by mentor_field enum value"),
    method: str | None = Query(None, description="Filter by meeting_method enum value"),
    search: str | None = Query(None, description="Search by mentor name"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Browse and filter mentors. Returns mentors who have filled in their profile."""
    # Fetch all mentors with their details
    query = (
        supabase.table("users")
        .select("id, name, avatar_url, mentor_details(*)")
        .eq("role", "MENTOR")
        .neq("id", str(user.id))
    )

    if search:
        query = query.ilike("name", f"*{search}*")

    all_mentors = query.execute()

    # Exclude mentors with ACCEPTED or PENDING follow relationship
    follow_result = (
        supabase.table("follows")
        .select("receiver_id")
        .eq("requester_id", str(user.id))
        .in_("status", ["ACCEPTED", "PENDING"])
        .execute()
    )
    exclude_ids = {row["receiver_id"] for row in follow_result.data or []}

    results: list[MentorSearchCard] = []
    for row in all_mentors.data or []:
        if str(row["id"]) in exclude_ids:
            continue

        details = row.get("mentor_details")
        if not details:
            continue

        # Filter by field if specified
        mentor_fields = details.get("fields") or []
        if field and field not in mentor_fields:
            continue

        # Filter by method if specified
        mentor_methods = details.get("methods") or []
        if method and method not in mentor_methods:
            continue

        results.append(
            MentorSearchCard(
                mentor_id=row["id"],
                name=row["name"],
                avatar_url=row.get("avatar_url"),
                introduction=details.get("introduction"),
                affiliation=details.get("affiliation"),
                expertise=details.get("expertise"),
                fields=details.get("fields"),
            )
        )

    total = len(results)
    page = results[offset : offset + limit]

    return MentorSearchResponse(mentors=page, total=total)


@router.get("/mentors/{mentor_id}", response_model=MentorProfileResponse)
async def get_mentor_detail(
    mentor_id: UUID,
    user: AuthenticatedUser,
):
    """Get a specific mentor's full profile."""
    user_result = (
        supabase.table("users")
        .select("id, name, avatar_url, role")
        .eq("id", str(mentor_id))
        .eq("role", "MENTOR")
        .maybe_single()
        .execute()
    )

    mentor_data = (user_result.data if user_result else None) or {}
    if not mentor_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mentor not found.",
        )

    details_result = (
        supabase.table("mentor_details")
        .select("*")
        .eq("user_id", str(mentor_id))
        .maybe_single()
        .execute()
    )

    row = (details_result.data if details_result else None) or {}
    return MentorProfileResponse(
        user_id=mentor_id,
        name=mentor_data["name"],
        avatar_url=mentor_data.get("avatar_url"),
        introduction=row.get("introduction"),
        affiliation=row.get("affiliation"),
        expertise=row.get("expertise"),
        fields=row.get("fields"),
        frequency=row.get("frequency"),
        available_days=row.get("available_days"),
        time_slots=row.get("time_slots"),
        methods=row.get("methods"),
        communication_styles=row.get("communication_styles"),
        mentoring_focuses=row.get("mentoring_focuses"),
    )


# ==================================================================
# Matching & Recommendations
# ==================================================================


@router.get("/recommendations", response_model=MentorRecommendationsResponse)
async def get_mentor_recommendations(
    user: AuthenticatedUser,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Get ranked mentor recommendations based on survey matching against mentor profiles."""

    # 1. Fetch mentee's latest survey
    mentee_result = (
        supabase.table("mentor_matching_surveys")
        .select("*")
        .eq("user_id", str(user.id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not mentee_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No survey found. Please complete the mentor matching survey first.",
        )

    mentee_survey = mentee_result.data[0]

    # 2. Fetch all mentor profiles with matching fields populated
    mentors_result = (
        supabase.table("users")
        .select("id, name, avatar_url, mentor_details(*)")
        .eq("role", "MENTOR")
        .neq("id", str(user.id))
        .execute()
    )

    if not mentors_result.data:
        return MentorRecommendationsResponse(recommendations=[], total=0)

    # 3. Count active mentees per mentor (ACCEPTED requests)
    mentor_ids = [row["id"] for row in mentors_result.data]
    active_requests = (
        supabase.table("mentoring_requests")
        .select("mentor_id")
        .in_("mentor_id", mentor_ids)
        .eq("status", "ACCEPTED")
        .execute()
    )
    # Build count map: mentor_id -> number of active mentees
    mentee_count: dict[str, int] = {}
    for req in active_requests.data or []:
        mid = req["mentor_id"]
        mentee_count[mid] = mentee_count.get(mid, 0) + 1

    # 4. Score each mentor who has matching fields filled in
    scored: list[tuple[float, MentorRecommendationCard]] = []

    for row in mentors_result.data:
        details = row.get("mentor_details")
        if not details or not details.get("fields"):
            continue

        result = _compute_match_score(mentee_survey, details)
        if result is None:
            continue

        total, breakdown = result
        if total < _MIN_MATCH_SCORE:
            continue

        # Apply new mentor boost: fewer active mentees → higher boost
        active = mentee_count.get(row["id"], 0)
        boost = _NEW_MENTOR_BOOST * max(0.0, 1.0 - active / _MENTEE_CAP)
        boosted_score = min(1.0, total + boost)

        card = MentorRecommendationCard(
            mentor_id=row["id"],
            name=row["name"],
            avatar_url=row.get("avatar_url"),
            introduction=details.get("introduction"),
            affiliation=details.get("affiliation"),
            expertise=details.get("expertise"),
            match_score=boosted_score,
            score_breakdown=breakdown,
        )
        scored.append((boosted_score, card))

    # 5. Sort by score descending, paginate
    scored.sort(key=lambda x: x[0], reverse=True)
    total_count = len(scored)
    page = scored[offset : offset + limit]

    return MentorRecommendationsResponse(
        recommendations=[card for _, card in page],
        total=total_count,
    )


# ==================================================================
# Mentoring Requests
# ==================================================================


def _build_request_response(req: dict, users_map: dict) -> MentoringRequestResponse:
    """Build a MentoringRequestResponse from a request row and a users lookup map."""
    mentee_data = users_map.get(req["mentee_id"], {})
    mentor_data = users_map.get(req["mentor_id"], {})

    return MentoringRequestResponse(
        id=req["id"],
        mentee=RequestUserInfo(
            id=req["mentee_id"],
            name=mentee_data.get("name", "Unknown"),
            avatar_url=mentee_data.get("avatar_url"),
        ),
        mentor=RequestUserInfo(
            id=req["mentor_id"],
            name=mentor_data.get("name", "Unknown"),
            avatar_url=mentor_data.get("avatar_url"),
        ),
        message=req.get("message"),
        status=req["status"],
        created_at=req["created_at"],
    )


@router.post(
    "/requests",
    response_model=MentoringRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mentoring_request(
    body: MentoringRequestCreate,
    user: AuthenticatedUser,
):
    """Submit a mentoring request to a mentor."""
    # Verify target is a mentor
    mentor_result = (
        supabase.table("users")
        .select("id, name, avatar_url, role")
        .eq("id", str(body.mentor_id))
        .eq("role", "MENTOR")
        .single()
        .execute()
    )

    if not mentor_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mentor not found.",
        )

    # Check for existing PENDING request
    existing = (
        supabase.table("mentoring_requests")
        .select("id")
        .eq("mentee_id", str(user.id))
        .eq("mentor_id", str(body.mentor_id))
        .eq("status", "PENDING")
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request to this mentor.",
        )

    # Create request
    result = (
        supabase.table("mentoring_requests")
        .insert(
            {
                "mentee_id": str(user.id),
                "mentor_id": str(body.mentor_id),
                "message": body.message,
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create mentoring request.",
        )

    # Notify mentor
    create_notification(
        recipient_id=body.mentor_id,
        notification_type=NotificationType.MENTORING_REQUEST,
        actor_id=user.id,
    )

    # Build response
    mentee_result = (
        supabase.table("users")
        .select("id, name, avatar_url")
        .eq("id", str(user.id))
        .single()
        .execute()
    )

    users_map = {
        str(user.id): mentee_result.data or {},
        str(body.mentor_id): mentor_result.data,
    }

    return _build_request_response(result.data[0], users_map)


@router.get("/requests/sent", response_model=MentoringRequestListResponse)
async def get_sent_requests(
    user: AuthenticatedUser,
    status_filter: str | None = Query(None, alias="status"),
):
    """Get mentoring requests sent by the current user (as mentee)."""
    query = (
        supabase.table("mentoring_requests")
        .select("*")
        .eq("mentee_id", str(user.id))
        .order("created_at", desc=True)
    )

    if status_filter:
        query = query.eq("status", status_filter)

    result = query.execute()
    requests = result.data or []

    if not requests:
        return MentoringRequestListResponse(requests=[], total=0)

    # Batch fetch user info
    user_ids = list(
        {r["mentee_id"] for r in requests} | {r["mentor_id"] for r in requests}
    )
    users_result = (
        supabase.table("users")
        .select("id, name, avatar_url")
        .in_("id", user_ids)
        .execute()
    )
    users_map = {row["id"]: row for row in users_result.data or []}

    return MentoringRequestListResponse(
        requests=[_build_request_response(r, users_map) for r in requests],
        total=len(requests),
    )


@router.get("/requests/received", response_model=MentoringRequestListResponse)
async def get_received_requests(
    user: AuthenticatedUser,
    status_filter: str | None = Query(None, alias="status"),
):
    """Get mentoring requests received by the current user (as mentor)."""
    query = (
        supabase.table("mentoring_requests")
        .select("*")
        .eq("mentor_id", str(user.id))
        .order("created_at", desc=True)
    )

    if status_filter:
        query = query.eq("status", status_filter)

    result = query.execute()
    requests = result.data or []

    if not requests:
        return MentoringRequestListResponse(requests=[], total=0)

    # Batch fetch user info
    user_ids = list(
        {r["mentee_id"] for r in requests} | {r["mentor_id"] for r in requests}
    )
    users_result = (
        supabase.table("users")
        .select("id, name, avatar_url")
        .in_("id", user_ids)
        .execute()
    )
    users_map = {row["id"]: row for row in users_result.data or []}

    return MentoringRequestListResponse(
        requests=[_build_request_response(r, users_map) for r in requests],
        total=len(requests),
    )


@router.post("/requests/{request_id}/accept", status_code=status.HTTP_200_OK)
async def accept_mentoring_request(
    request_id: UUID,
    user: AuthenticatedUser,
):
    """Accept a mentoring request (mentor only)."""
    existing = (
        supabase.table("mentoring_requests")
        .select("id, mentee_id, mentor_id, status")
        .eq("id", str(request_id))
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found.",
        )

    if existing.data["mentor_id"] != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the mentor can accept this request.",
        )

    if existing.data["status"] != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {existing.data['status'].lower()}.",
        )

    supabase.table("mentoring_requests").update({"status": "ACCEPTED"}).eq(
        "id", str(request_id)
    ).execute()

    # Notify mentee
    create_notification(
        recipient_id=UUID(existing.data["mentee_id"]),
        notification_type=NotificationType.MENTORING_ACCEPTED,
        actor_id=user.id,
    )

    return {"message": "Mentoring request accepted"}


@router.post("/requests/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_mentoring_request(
    request_id: UUID,
    user: AuthenticatedUser,
):
    """Reject a mentoring request (mentor only)."""
    existing = (
        supabase.table("mentoring_requests")
        .select("id, mentee_id, mentor_id, status")
        .eq("id", str(request_id))
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found.",
        )

    if existing.data["mentor_id"] != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the mentor can reject this request.",
        )

    if existing.data["status"] != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request is already {existing.data['status'].lower()}.",
        )

    supabase.table("mentoring_requests").update({"status": "REJECTED"}).eq(
        "id", str(request_id)
    ).execute()

    return {"message": "Mentoring request rejected"}
