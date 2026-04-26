from aiogram import Router

from .menu import router as menu_router
from .header import router as header_router

router = Router()

router.include_router(menu_router)
router.include_router(header_router)
