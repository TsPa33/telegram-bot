from aiogram import Router

from .start import router as start_router
from .search import router as search_router
from .pagination import router as pagination_router


router = Router()

# 1. Базові entry точки
router.include_router(start_router)

# 3. Потім загальні (cars/search)
router.include_router(search_router)

# 4. Найзагальніші (pagination / fallback)
router.include_router(pagination_router)
