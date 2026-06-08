import logging

from aiogram import Router

from .cars import router as cars_router
from .verification import router as verification_router
from .onboarding import router as onboarding_router
from .payment import router as payment_router
from .profile import router as profile_router
from .add_car import router as add_car_router
from .site import router as site_router
from .services import router as services_router
from .crm import router as crm_router
from .leads import router as leads_router
from .parts import router as parts_router

logger = logging.getLogger(__name__)

router = Router()

logger.info("CRM router loaded id=%s", id(crm_router))

# Підключення всіх seller-роутерів
# Захист від повторного attach при подвійних імпортах (seller vs seller.__init__)
def _include_once(parent: Router, child: Router, name: str) -> None:
    current_parent = getattr(child, "parent_router", None)
    if current_parent is None:
        if child is crm_router:
            logger.info("Including crm_router into seller_router parent_id=%s child_id=%s", id(parent), id(child))
        parent.include_router(child)
    else:
        logger.info(
            "Skip include for %s: already attached parent_id=%s child_id=%s",
            name,
            id(current_parent),
            id(child),
        )


for _name, _child in (
    ("onboarding_router", onboarding_router),
    ("crm_router", crm_router),
    ("add_car_router", add_car_router),
    ("cars_router", cars_router),
    ("profile_router", profile_router),
    ("verification_router", verification_router),
    ("payment_router", payment_router),
    ("leads_router", leads_router),
    ("services_router", services_router),
    ("site_router", site_router),
    ("parts_router", parts_router),
):
    _include_once(router, _child, _name)
