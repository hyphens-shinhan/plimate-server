from fastapi import APIRouter, HTTPException, Query, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.networking import (
    FriendCard,
    MyFriendsResponse,
    NearbyUserCard,
    NearbyUsersResponse,
    RecommendationsResponse,
    RecommendedUserCard,
)

router = APIRouter(prefix="/networking", tags=["networking"])


def _get_blocked_user_ids(user_id: str) -> set[str]:
    """Get all user IDs involved in blocks with current user."""
    result = (
        supabase.table("blocks")
        .select("blocker_id, blocked_id")
        .or_(f"blocker_id.eq.{user_id},blocked_id.eq.{user_id}")
        .execute()
    )

    blocked_ids = set()
    for block in result.data or []:
        blocked_ids.add(block["blocker_id"])
        blocked_ids.add(block["blocked_id"])
    blocked_ids.discard(user_id)
    return blocked_ids


def _get_my_friend_ids(user_id: str) -> set[str]:
    """Get all friend IDs (ACCEPTED follows in both directions)."""
    as_requester = (
        supabase.table("follows")
        .select("receiver_id")
        .eq("requester_id", user_id)
        .eq("status", "ACCEPTED")
        .execute()
    )

    as_receiver = (
        supabase.table("follows")
        .select("requester_id")
        .eq("receiver_id", user_id)
        .eq("status", "ACCEPTED")
        .execute()
    )

    friend_ids = set()
    for row in as_requester.data or []:
        friend_ids.add(row["receiver_id"])
    for row in as_receiver.data or []:
        friend_ids.add(row["requester_id"])

    return friend_ids


@router.get("/nearby", response_model=NearbyUsersResponse)
async def get_nearby_users(
    user: AuthenticatedUser,
    radius_km: float = Query(10.0, ge=1.0, le=100.0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get users near current user's location for map display (PostGIS)."""
    # Get current user's location
    my_profile = (
        supabase.table("user_profiles")
        .select("latitude, longitude")
        .eq("user_id", str(user.id))
        .single()
        .execute()
    )

    if not my_profile.data or not my_profile.data.get("latitude"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your location is not set. Please update your profile.",
        )

    my_lat = my_profile.data["latitude"]
    my_lng = my_profile.data["longitude"]

    # Get blocked user IDs
    blocked_ids = _get_blocked_user_ids(str(user.id))

    # PostGIS RPC: ST_DWithin + ST_Distance with spatial index
    result = supabase.rpc(
        "get_nearby_users",
        {
            "center_lat": my_lat,
            "center_lng": my_lng,
            "radius_meters": radius_km * 1000.0,
            "excluded_ids": list(blocked_ids),
            "requesting_user_id": str(user.id),
            "result_limit": limit,
            "result_offset": offset,
        },
    ).execute()

    data = result.data

    nearby_users = [
        NearbyUserCard(
            id=row["id"],
            name=row["name"],
            avatar_url=row.get("avatar_url"),
            affiliation=row.get("affiliation"),
            latitude=row["latitude"],
            longitude=row["longitude"],
            distance_km=float(row["distance_km"]),
        )
        for row in data["users"]
    ]

    return NearbyUsersResponse(
        users=nearby_users,
        total=data["total"],
        center_lat=my_lat,
        center_lng=my_lng,
        radius_km=radius_km,
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_friend_recommendations(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Get friend recommendations based on friends of friends, or random users if none."""
    # Get my direct friends
    my_friend_ids = _get_my_friend_ids(str(user.id))

    # Get blocked user IDs
    blocked_ids = _get_blocked_user_ids(str(user.id))

    # Get friend names and avatars for mutual friends display
    friend_info: dict[str, dict] = {}  # friend_id -> {name, avatar_url}
    if my_friend_ids:
        friends_result = (
            supabase.table("users")
            .select("id, name, avatar_url")
            .in_("id", list(my_friend_ids))
            .execute()
        )
        for f in friends_result.data or []:
            friend_info[str(f["id"])] = {
                "name": f["name"],
                "avatar_url": f.get("avatar_url"),
            }

    # Find friends of friends
    friends_of_friends: dict[str, set[str]] = {}  # candidate_id -> set of mutual friend IDs

    for friend_id in my_friend_ids:
        # Get this friend's friends as requester
        fof_as_requester = (
            supabase.table("follows")
            .select("receiver_id")
            .eq("requester_id", friend_id)
            .eq("status", "ACCEPTED")
            .execute()
        )

        # Get this friend's friends as receiver
        fof_as_receiver = (
            supabase.table("follows")
            .select("requester_id")
            .eq("receiver_id", friend_id)
            .eq("status", "ACCEPTED")
            .execute()
        )

        for row in fof_as_requester.data or []:
            candidate_id = row["receiver_id"]
            if (
                candidate_id != str(user.id)
                and candidate_id not in my_friend_ids
                and candidate_id not in blocked_ids
            ):
                if candidate_id not in friends_of_friends:
                    friends_of_friends[candidate_id] = set()
                friends_of_friends[candidate_id].add(friend_id)

        for row in fof_as_receiver.data or []:
            candidate_id = row["requester_id"]
            if (
                candidate_id != str(user.id)
                and candidate_id not in my_friend_ids
                and candidate_id not in blocked_ids
            ):
                if candidate_id not in friends_of_friends:
                    friends_of_friends[candidate_id] = set()
                friends_of_friends[candidate_id].add(friend_id)

    recommendations = []

    if friends_of_friends:
        # Get user details for candidates with mutual friends
        candidate_ids = list(friends_of_friends.keys())
        users_result = (
            supabase.table("users")
            .select("id, name, avatar_url, user_profiles(affiliation)")
            .in_("id", candidate_ids)
            .execute()
        )

        # Build recommendations from friends of friends
        for row in users_result.data or []:
            user_id = str(row["id"])
            mutual_friend_ids = list(friends_of_friends.get(user_id, set()))[:3]
            mutual_friends_list = [friend_info.get(fid, {}).get("name", "Unknown") for fid in mutual_friend_ids]
            mutual_friends_avatars = [friend_info.get(fid, {}).get("avatar_url") for fid in mutual_friend_ids]
            # Filter out None avatars
            mutual_friends_avatars = [a for a in mutual_friends_avatars if a]

            profile = row.get("user_profiles") or {}
            recommendations.append(
                RecommendedUserCard(
                    id=row["id"],
                    name=row["name"],
                    avatar_url=row.get("avatar_url"),
                    affiliation=profile.get("affiliation"),
                    mutual_friends_count=len(friends_of_friends.get(user_id, set())),
                    mutual_friends=mutual_friends_list if mutual_friends_list else None,
                    mutual_friends_avatars=mutual_friends_avatars if mutual_friends_avatars else None,
                )
            )

        # Sort by mutual friends count descending
        recommendations.sort(key=lambda u: u.mutual_friends_count, reverse=True)
    else:
        # No mutual friends - return random users (excluding admins, self, friends, blocked)
        exclude_ids = list(blocked_ids | my_friend_ids | {str(user.id)})

        random_users_result = (
            supabase.table("users")
            .select("id, name, avatar_url, role, user_profiles(affiliation)")
            .neq("role", "ADMIN")
            .execute()
        )

        for row in random_users_result.data or []:
            if str(row["id"]) in exclude_ids:
                continue

            profile = row.get("user_profiles") or {}
            recommendations.append(
                RecommendedUserCard(
                    id=row["id"],
                    name=row["name"],
                    avatar_url=row.get("avatar_url"),
                    affiliation=profile.get("affiliation"),
                    mutual_friends_count=0,
                    mutual_friends=None,
                    mutual_friends_avatars=None,
                )
            )

    total = len(recommendations)
    recommendations = recommendations[offset : offset + limit]

    return RecommendationsResponse(users=recommendations, total=total)


@router.get("/friends", response_model=MyFriendsResponse)
async def get_my_friends(
    user: AuthenticatedUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
):
    """Get current user's friends list."""
    # Get friends where I am requester
    friends_as_requester = (
        supabase.table("follows")
        .select(
            "receiver_id, accepted_at, "
            "users!follows_receiver_id_fkey(id, name, avatar_url, role, user_profiles(affiliation, scholarship_batch))"
        )
        .eq("requester_id", str(user.id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    # Get friends where I am receiver
    friends_as_receiver = (
        supabase.table("follows")
        .select(
            "requester_id, accepted_at, "
            "users!follows_requester_id_fkey(id, name, avatar_url, role, user_profiles(affiliation, scholarship_batch))"
        )
        .eq("receiver_id", str(user.id))
        .eq("status", "ACCEPTED")
        .execute()
    )

    friends = []

    for row in friends_as_requester.data or []:
        user_data = row.get("users")
        if user_data:
            profile = user_data.get("user_profiles") or {}
            name = user_data["name"]
            friend_id = str(user_data["id"])

            if search and search.lower() not in name.lower():
                continue

            friends.append(
                FriendCard(
                    id=user_data["id"],
                    name=name,
                    avatar_url=user_data.get("avatar_url"),
                    affiliation=profile.get("affiliation"),
                    role=user_data.get("role"),
                    scholarship_batch=profile.get("scholarship_batch"),
                    connected_at=row["accepted_at"],
                )
            )

    for row in friends_as_receiver.data or []:
        user_data = row.get("users")
        if user_data:
            profile = user_data.get("user_profiles") or {}
            name = user_data["name"]
            friend_id = str(user_data["id"])

            if search and search.lower() not in name.lower():
                continue

            friends.append(
                FriendCard(
                    id=user_data["id"],
                    name=name,
                    avatar_url=user_data.get("avatar_url"),
                    affiliation=profile.get("affiliation"),
                    role=user_data.get("role"),
                    scholarship_batch=profile.get("scholarship_batch"),
                    connected_at=row["accepted_at"],
                )
            )

    # Sort by connected_at descending
    friends.sort(key=lambda f: f.connected_at, reverse=True)
    total = len(friends)
    friends = friends[offset : offset + limit]

    return MyFriendsResponse(friends=friends, total=total)
