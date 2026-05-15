from aiogram import Router

from .cars import router as cars_router
from .verification import router as verification_router
from .payment import router as payment_router
from .profile import router as profile_router
from .add_car import router as add_car_router
from .site import router as site_router
from .services import router as services_router
from .crm import router as crm_router

router = Router()

# Підключення всіх seller-роутерів
router.include_router(add_car_router)
router.include_router(cars_router)
router.include_router(profile_router)
router.include_router(verification_router)
router.include_router(payment_router)
router.include_router(crm_router)
router.include_router(services_router)
router.include_router(site_router)
