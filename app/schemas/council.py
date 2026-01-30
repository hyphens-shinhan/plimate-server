from uuid import UUID

from pydantic import BaseModel


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

    class Config:
        from_attributes = True


class CouncilListResponse(BaseModel):
    councils: list[CouncilResponse]
    total: int
