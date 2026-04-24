from aiogram import Router

from ..seller import router as seller_main_router  # ✅ ГОЛОВНИЙ
from .cars import router as cars_router
from .verification import router as verification_router
from .payment import router as payment_router
from .profile import router as profile_router

router = Router()

# 🔥 ГОЛОВНИЙ FLOW
router.include_router(seller_main_router)

# інші
router.include_router(cars_router)
router.include_router(profile_router)
router.include_router(verification_router)
router.include_router(payment_router)
