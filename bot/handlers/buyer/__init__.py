from aiogram import Router

from .start import router as start_router
from .search import router as search_router
from .pagination import router as pagination_router


router = Router()

router.include_router(start_router)
router.include_router(search_router)
router.include_router(pagination_router)
