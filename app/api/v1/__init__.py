from fastapi import APIRouter

from app.api.v1 import (
    users,
    follows,
    blocks,
    posts,
    comments,
    clubs,
    councils,
    reports,
    chats,
    notifications,
    academic,
)

router = APIRouter(prefix="/api/v1")

router.include_router(users.router)
router.include_router(follows.router)
router.include_router(blocks.router)
router.include_router(posts.router)
router.include_router(comments.router)
router.include_router(clubs.router)
router.include_router(councils.router)
router.include_router(reports.router)
router.include_router(chats.router)
router.include_router(notifications.router)
router.include_router(academic.router)
