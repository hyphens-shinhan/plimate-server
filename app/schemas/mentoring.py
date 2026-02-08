from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class MentorField(str, Enum):
    CAREER_EMPLOYMENT = "CAREER_EMPLOYMENT"
    ACADEMICS_STUDY = "ACADEMICS_STUDY"
    ENTREPRENEURSHIP_LEADERSHIP = "ENTREPRENEURSHIP_LEADERSHIP"
    SELF_DEVELOPMENT_HOBBIES = "SELF_DEVELOPMENT_HOBBIES"
    VOLUNTEERING_SOCIAL = "VOLUNTEERING_SOCIAL"
    EMOTIONAL_COUNSELING = "EMOTIONAL_COUNSELING"
    INVESTMENT_FINANCE = "INVESTMENT_FINANCE"


class MeetingFrequency(str, Enum):
    ONE_TIME = "ONE_TIME"
    MONTHLY = "MONTHLY"
    LONG_TERM = "LONG_TERM"


class AvailableDay(str, Enum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


class TimeSlot(str, Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    LATE_AFTERNOON = "LATE_AFTERNOON"
    EVENING = "EVENING"


class MeetingMethod(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    FLEXIBLE = "FLEXIBLE"


class CommunicationStyle(str, Enum):
    DIRECT_CLEAR = "DIRECT_CLEAR"
    SOFT_SUPPORTIVE = "SOFT_SUPPORTIVE"
    HORIZONTAL_COMFORTABLE = "HORIZONTAL_COMFORTABLE"
    EXPERIENCE_GUIDE = "EXPERIENCE_GUIDE"


class MentoringFocus(str, Enum):
    PRACTICE_ORIENTED = "PRACTICE_ORIENTED"
    ADVICE_COUNSELING = "ADVICE_COUNSELING"
    INSIGHT_INSPIRATION = "INSIGHT_INSPIRATION"


class MentorMatchingSurveyCreate(BaseModel):
    fields: list[MentorField] = Field(..., min_length=1)
    frequency: MeetingFrequency
    goal: str = Field(..., min_length=1, max_length=1000)
    available_days: list[AvailableDay] = Field(..., min_length=1)
    time_slots: list[TimeSlot] = Field(..., min_length=1)
    methods: list[MeetingMethod] = Field(..., min_length=1)
    communication_styles: list[CommunicationStyle] = Field(..., min_length=1)
    mentoring_focuses: list[MentoringFocus] = Field(..., min_length=1)


class MentorMatchingSurveyResponse(BaseModel):
    id: UUID
    user_id: UUID
    fields: list[MentorField]
    frequency: MeetingFrequency
    goal: str
    available_days: list[AvailableDay]
    time_slots: list[TimeSlot]
    methods: list[MeetingMethod]
    communication_styles: list[CommunicationStyle]
    mentoring_focuses: list[MentoringFocus]
    created_at: datetime
    updated_at: datetime


class MatchScoreBreakdown(BaseModel):
    fields: float
    frequency: float
    available_days: float
    time_slots: float
    methods: float
    communication_styles: float
    mentoring_focuses: float


class MentorRecommendationCard(BaseModel):
    mentor_id: UUID
    name: str
    avatar_url: str | None = None
    introduction: str | None = None
    affiliation: str | None = None
    expertise: list[str] | None = None
    match_score: float
    score_breakdown: MatchScoreBreakdown


class MentorRecommendationsResponse(BaseModel):
    recommendations: list[MentorRecommendationCard]
    total: int
