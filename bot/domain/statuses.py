"""Central status/action constants and pure normalization helpers."""

SELLER_LEAD_ACTION_VIEWED = "viewed"
SELLER_LEAD_ACTION_SKIPPED = "skipped"
SELLER_LEAD_ACTION_OFFERED = "offered"
SELLER_LEAD_ACTION_DECLINED = "declined"

SELLER_LEAD_ACTIONS = {
    "viewed",
    "skipped",
    "offered",
    "declined",
}

BUYER_OFFER_STATUS_PENDING = "pending"
BUYER_OFFER_STATUS_ACCEPTED = "accepted"
BUYER_OFFER_STATUS_REJECTED = "rejected"

BUYER_OFFER_STATUSES = {
    "pending",
    "accepted",
    "rejected",
}

MARKETPLACE_MATCH_STATUS_MATCHED = "matched"
MARKETPLACE_MATCH_STATUS_CONTACTED = "contacted"
MARKETPLACE_MATCH_STATUS_CLOSED = "closed"
MARKETPLACE_MATCH_STATUS_CANCELLED = "cancelled"

MARKETPLACE_MATCH_STATUSES = {
    "matched",
    "contacted",
    "closed",
    "cancelled",
}

MARKETPLACE_REQUEST_STATUS_PENDING = "pending"
MARKETPLACE_REQUEST_STATUS_ACTIVE = "active"
MARKETPLACE_REQUEST_STATUS_MATCHED = "matched"
MARKETPLACE_REQUEST_STATUS_CLOSED = "closed"

MARKETPLACE_REQUEST_STATUSES = {
    "pending",
    "active",
    "matched",
    "closed",
}

NOTIFICATION_STATUS_PENDING = "pending"
NOTIFICATION_STATUS_SENT = "sent"
NOTIFICATION_STATUS_FAILED = "failed"
NOTIFICATION_STATUS_CANCELLED = "cancelled"

NOTIFICATION_STATUSES = {
    "pending",
    "sent",
    "failed",
    "cancelled",
}

CRM_LEAD_STATUS_NEW = "new"
CRM_LEAD_STATUS_IN_WORK = "in_work"
CRM_LEAD_STATUS_REPLIED = "replied"
CRM_LEAD_STATUS_SELECTED = "selected"
CRM_LEAD_STATUS_DECLINED = "declined"
CRM_LEAD_STATUS_SKIPPED = "skipped"

CRM_LEAD_STATUSES = {
    "new",
    "in_work",
    "replied",
    "selected",
    "declined",
    "skipped",
}

CRM_OFFER_STATUS_ACTIVE = "active"
CRM_OFFER_STATUS_SELECTED = "selected"
CRM_OFFER_STATUS_REJECTED = "rejected"
CRM_OFFER_STATUS_ALL = "all"

CRM_OFFER_STATUSES = {
    "active",
    "selected",
    "rejected",
    "all",
}

CAR_STATUS_ACTIVE_VALUES = {
    "1",
    "active",
    "enabled",
    "published",
    "true",
}

CAR_STATUS_INACTIVE_VALUES = {
    "0",
    "inactive",
    "disabled",
    "archived",
    "false",
}

SERVICE_ACTIVE_VALUES = {
    "1",
    "active",
    "enabled",
    "published",
    "true",
}

SERVICE_INACTIVE_VALUES = {
    "0",
    "inactive",
    "disabled",
    "archived",
    "false",
}


def normalize_text_status(value: object, default: str = "") -> str:
    """Return a lowercase stripped text status, with safe bool/None handling."""
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    return text if text else default


def is_car_active_status(value: object) -> bool:
    return normalize_text_status(value) in CAR_STATUS_ACTIVE_VALUES


def is_service_active_status(value: object) -> bool:
    return normalize_text_status(value) in SERVICE_ACTIVE_VALUES


def is_valid_seller_lead_action(value: str) -> bool:
    return value in SELLER_LEAD_ACTIONS


def is_valid_buyer_offer_status(value: str) -> bool:
    return value in BUYER_OFFER_STATUSES


def is_valid_marketplace_match_status(value: str) -> bool:
    return value in MARKETPLACE_MATCH_STATUSES


def is_valid_notification_status(value: str) -> bool:
    return value in NOTIFICATION_STATUSES


def is_valid_crm_lead_status(value: str) -> bool:
    return value in CRM_LEAD_STATUSES


def is_valid_crm_offer_status(value: str) -> bool:
    return value in CRM_OFFER_STATUSES
