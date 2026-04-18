from aiogram import Router

from .add_car import router as add_car_router
from .cars import router as cars_router
from .verification import router as verification_router  # ✅ ДОДАНО


router = Router()

# Порядок важливий:
# спочатку FSM (add_car), потім інші

router.include_router(add_car_router)
router.include_router(cars_router)
router.include_router(verification_router)  # ✅ ДОДАНО
