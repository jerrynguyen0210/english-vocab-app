"""Version-one vocabulary API router."""

from fastapi import APIRouter

from app.api.routes import account, common_words, reviews, words

router = APIRouter()
router.include_router(words.router)
router.include_router(common_words.router)
router.include_router(reviews.router)
router.include_router(account.router)
