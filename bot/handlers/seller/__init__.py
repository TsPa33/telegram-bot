from aiogram import Router

# from .add_car import router as add_car_router  # ❌ вимкнено
from .cars import router as cars_router
from .verification import router as verification_router
from .payment import router as payment_router
from .profile import router as profile_router  # ✅ ДОДАТИ

router = Router()

# порядок важливий
from aiogram import Router

# from .add_car import router as add_car_router  # ❌ вимкнено
from .cars import router as cars_router
from .verification import router as verification_router
from .payment import router as payment_router
from .profile import router as profile_router

router = Router()

# router.include_router(add_car_router)  # ❌ вимкнено
router.include_router(cars_router)
router.include_router(profile_router)
router.include_router(verification_router)
router.include_router(payment_router)
router.include_router(cars_router)
router.include_router(profile_router)      # ✅ ДОДАТИ СЮДИ
router.include_router(verification_router)
router.include_router(payment_router)
