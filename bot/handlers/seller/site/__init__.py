from aiogram import Router

from .banner import router as banner_router
from .header import router as header_router
from .logo import router as logo_router
from .media import router as media_router
from .menu import router as menu_router
from .modules import router as modules_router

router = Router()

router.include_router(menu_router)
router.include_router(header_router)
router.include_router(banner_router)
router.include_router(logo_router)
router.include_router(media_router)
router.include_router(modules_router)
