from aiogram import Router
from .menu import router as menu_router

router = Router()

router.include_router(menu_router)
