from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.mentoring import (
    MatchScoreBreakdown,
    MentorMatchingSurveyCreate,
    MentorMatchingSurveyResponse,
    MentorRecommendationCard,
    MentorRecommendationsResponse,
)

router = APIRouter(prefix="/mentoring", tags=["mentoring"])

# Weights for each matching dimension
_WEIGHTS = {
    "fields": 0.25,
    "frequency": 0.10,
    "available_days": 0.15,
    "time_slots": 0.15,
    "methods": 0.10,
    "communication_styles": 0.15,
    "mentoring_focuses": 0.10,
}


def _compute_match_score(
    mentee: dict, mentor: dict
) -> tuple[float, MatchScoreBreakdown]:
    """Compute weighted match score between a mentee survey and a mentor survey.

    Returns (total_score, breakdown) where total_score is 0.0-1.0.
    """
    # Step 1 — Fields: Jaccard similarity (symmetric)
    mentee_fields = set(mentee["fields"])
    mentor_fields = set(mentor["fields"])
    union = mentee_fields | mentor_fields
    fields_score = len(mentee_fields & mentor_fields) / len(union) if union else 0.0

    # Step 2 — Frequency: exact match
    frequency_score = 1.0 if mentee["frequency"] == mentor["frequency"] else 0.0

    # Step 4 — Available days: mentee-coverage ratio
    mentee_days = set(mentee["available_days"])
    mentor_days = set(mentor["available_days"])
    days_score = (
        len(mentee_days & mentor_days) / len(mentee_days) if mentee_days else 0.0
    )

    # Step 5 — Time slots: mentee-coverage ratio
    mentee_slots = set(mentee["time_slots"])
    mentor_slots = set(mentor["time_slots"])
    slots_score = (
        len(mentee_slots & mentor_slots) / len(mentee_slots) if mentee_slots else 0.0
    )

    # Step 6 — Methods: FLEXIBLE acts as wildcard, binary overlap
    mentee_methods = set(mentee["methods"])
    mentor_methods = set(mentor["methods"])
    if "FLEXIBLE" in mentee_methods or "FLEXIBLE" in mentor_methods:
        methods_score = 1.0
    else:
        methods_score = 1.0 if mentee_methods & mentor_methods else 0.0

    # Step 7A — Communication styles: mentee-coverage ratio
    mentee_styles = set(mentee["communication_styles"])
    mentor_styles = set(mentor["communication_styles"])
    styles_score = (
        len(mentee_styles & mentor_styles) / len(mentee_styles)
        if mentee_styles
        else 0.0
    )

    # Step 7B — Mentoring focuses: mentee-coverage ratio
    mentee_focuses = set(mentee["mentoring_focuses"])
    mentor_focuses = set(mentor["mentoring_focuses"])
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


@router.get("/recommendations", response_model=MentorRecommendationsResponse)
async def get_mentor_recommendations(
    user: AuthenticatedUser,
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Get ranked mentor recommendations based on survey matching."""

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

    # 2. Fetch all mentor user IDs
    mentors_result = (
        supabase.table("users")
        .select("id")
        .eq("role", "MENTOR")
        .neq("id", str(user.id))
        .execute()
    )

    if not mentors_result.data:
        return MentorRecommendationsResponse(recommendations=[], total=0)

    mentor_ids = [row["id"] for row in mentors_result.data]

    # 3. Fetch latest survey per mentor (batch)
    surveys_result = (
        supabase.table("mentor_matching_surveys")
        .select("*")
        .in_("user_id", mentor_ids)
        .order("created_at", desc=True)
        .execute()
    )

    # Deduplicate: keep only the latest survey per mentor
    latest_surveys: dict[str, dict] = {}
    for survey in surveys_result.data or []:
        uid = survey["user_id"]
        if uid not in latest_surveys:
            latest_surveys[uid] = survey

    if not latest_surveys:
        return MentorRecommendationsResponse(recommendations=[], total=0)

    # 4. Fetch mentor profiles and details (batch)
    matched_ids = list(latest_surveys.keys())

    users_result = (
        supabase.table("users")
        .select("id, name, avatar_url")
        .in_("id", matched_ids)
        .execute()
    )
    user_map = {row["id"]: row for row in users_result.data or []}

    details_result = (
        supabase.table("mentor_details")
        .select("user_id, introduction, affiliation, expertise")
        .in_("user_id", matched_ids)
        .execute()
    )
    details_map = {row["user_id"]: row for row in details_result.data or []}

    # 5. Score each mentor
    scored: list[tuple[float, MentorRecommendationCard]] = []

    for mentor_id, mentor_survey in latest_surveys.items():
        total, breakdown = _compute_match_score(mentee_survey, mentor_survey)

        mentor_user = user_map.get(mentor_id, {})
        mentor_detail = details_map.get(mentor_id, {})

        card = MentorRecommendationCard(
            mentor_id=mentor_id,
            name=mentor_user.get("name", "Unknown"),
            avatar_url=mentor_user.get("avatar_url"),
            introduction=mentor_detail.get("introduction"),
            affiliation=mentor_detail.get("affiliation"),
            expertise=mentor_detail.get("expertise"),
            match_score=total,
            score_breakdown=breakdown,
        )
        scored.append((total, card))

    # 6. Sort by score descending, paginate
    scored.sort(key=lambda x: x[0], reverse=True)
    total_count = len(scored)
    page = scored[offset : offset + limit]

    return MentorRecommendationsResponse(
        recommendations=[card for _, card in page],
        total=total_count,
    )
