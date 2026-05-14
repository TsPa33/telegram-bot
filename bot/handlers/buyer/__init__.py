from aiogram import Router

from .start import router as start_router
from .search import router as search_router
from .services import router as services_router
from .crm import router as crm_router
from .pagination import router as pagination_router


router = Router()

# 1. Базові entry точки
router.include_router(start_router)

# 2. Послуги
router.include_router(services_router)

# 3. Buyer CRM
router.include_router(crm_router)

# 4. Потім загальні (cars/search)
router.include_router(search_router)

# 5. Найзагальніші (pagination / fallback)
router.include_router(pagination_router)
