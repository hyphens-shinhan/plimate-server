from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NetworkingUserCard(BaseModel):
    id: UUID
    name: str
    avatar_url: str | None = None
    affiliation: str | None = None


class NearbyUserCard(NetworkingUserCard):
    latitude: float
    longitude: float
    distance_km: float


class RecommendedUserCard(NetworkingUserCard):
    mutual_friends_count: int
    mutual_friends: list[str] | None = None


class FriendCard(NetworkingUserCard):
    role: str | None = None
    scholarship_batch: int | None = None
    connected_at: datetime


class NearbyUsersResponse(BaseModel):
    users: list[NearbyUserCard]
    total: int
    center_lat: float
    center_lng: float
    radius_km: float


class RecommendationsResponse(BaseModel):
    users: list[RecommendedUserCard]
    total: int


class MyFriendsResponse(BaseModel):
    friends: list[FriendCard]
    total: int
