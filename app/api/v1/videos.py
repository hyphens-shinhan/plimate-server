import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.video import VideoCreate, VideoListResponse, VideoResponse

router = APIRouter(prefix="/videos", tags=["videos"])

_YT_PATTERN = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([a-zA-Z0-9_-]{11})"
)


def _extract_thumbnail(url: str) -> str | None:
    m = _YT_PATTERN.search(url)
    if not m:
        return None
    return f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg"


async def _check_admin(user_id: str):
    try:
        user_data = (
            supabase.table("users")
            .select("role")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not user_data.data or user_data.data["role"] != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can perform this action",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify admin status: {str(e)}",
        )


@router.get("", response_model=VideoListResponse)
async def get_videos(user: AuthenticatedUser):
    """Get all video links, newest first."""
    try:
        result = (
            supabase.table("videos")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        videos = [VideoResponse(**row) for row in result.data or []]
        return VideoListResponse(videos=videos, total=len(videos))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def create_video(video: VideoCreate, user: AuthenticatedUser):
    """Upload a new video link. Admin only."""
    await _check_admin(str(user.id))

    try:
        data = video.model_dump()
        data["thumbnail_url"] = _extract_thumbnail(video.url)

        result = (
            supabase.table("videos")
            .insert(data)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create video",
            )

        return VideoResponse(**result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
async def delete_video(video_id: UUID, user: AuthenticatedUser):
    """Delete a video link. Admin only."""
    await _check_admin(str(user.id))

    try:
        result = (
            supabase.table("videos")
            .delete()
            .eq("id", str(video_id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
            )

        return {"message": "Video deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
