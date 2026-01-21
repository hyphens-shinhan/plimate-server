from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase_auth import UserResponse

from app.core.database import supabase

security = HTTPBearer(
    scheme_name="Access Token",
)


class CurrentUser(BaseModel):
    id: UUID
    email: str


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> CurrentUser:
    token = credentials.credentials

    try:
        user_response: UserResponse = supabase.auth.get_user(token)

        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return CurrentUser(
            id=UUID(user_response.user.id), email=user_response.user.email
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
