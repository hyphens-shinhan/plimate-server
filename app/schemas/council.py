from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CouncilCreate(BaseModel):
    year: int
    affiliation: str
    region: str
    leader_id: UUID | None = None


class CouncilUpdate(BaseModel):
    year: int | None = None
    affiliation: str | None = None
    region: str | None = None
    leader_id: UUID | None = None


class CouncilResponse(BaseModel):
    id: UUID
    year: int
    affiliation: str
    region: str
    member_count: int
    leader_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class CouncilListResponse(BaseModel):
    councils: list[CouncilResponse]
    total: int


class CouncilMemberResponse(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None
    is_leader: bool = False


class MonthActivityStatus(BaseModel):
    submitted: bool
    report_id: UUID | None = None
    title: str | None = None


class CouncilActivity(BaseModel):
    id: UUID
    year: int
    affiliation: str
    region: str
    member_count: int
    activity_status: dict[int, MonthActivityStatus]
    leader_id: UUID | None


class CouncilActivityResponse(BaseModel):
    year: int
    councils: list[CouncilActivity]
