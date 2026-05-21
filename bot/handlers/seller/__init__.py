from aiogram import Router

from .cars import router as cars_router
from .verification import router as verification_router
from .payment import router as payment_router
from .profile import router as profile_router
from .add_car import router as add_car_router
from .site import router as site_router
from .services import router as services_router
from .crm import router as crm_router
from .leads import router as leads_router

router = Router()

# Підключення всіх seller-роутерів
# Захист від повторного attach при подвійних імпортах (seller vs seller.__init__)
def _include_once(parent: Router, child: Router) -> None:
    if getattr(child, "parent_router", None) is None:
        parent.include_router(child)


for _child in (
    crm_router,
    add_car_router,
    cars_router,
    profile_router,
    verification_router,
    payment_router,
    leads_router,
    services_router,
    site_router,
):
    _include_once(router, _child)
