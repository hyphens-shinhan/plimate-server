from fastapi import APIRouter

from app.api.v1 import users, follows

router = APIRouter(prefix="/api/v1")

router.include_router(users.router)
router.include_router(follows.router)
