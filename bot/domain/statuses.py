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


_CRM_LEAD_STATUS_META = {
    CRM_LEAD_STATUS_NEW: {"label": "Нова", "css_class": "status-new", "priority": 10},
    CRM_LEAD_STATUS_IN_WORK: {"label": "В роботі", "css_class": "status-viewed", "priority": 20},
    CRM_LEAD_STATUS_REPLIED: {"label": "Відповіли", "css_class": "status-replied", "priority": 30},
    CRM_LEAD_STATUS_SELECTED: {"label": "Обрано", "css_class": "status-success", "priority": 40},
    CRM_LEAD_STATUS_DECLINED: {"label": "Відхилено", "css_class": "status-rejected", "priority": 50},
    CRM_LEAD_STATUS_SKIPPED: {"label": "Пропущено", "css_class": "status-rejected", "priority": 60},
}

_CRM_OFFER_STATUS_META = {
    CRM_OFFER_STATUS_ACTIVE: {"label": "Активна", "css_class": "status-waiting", "priority": 10},
    BUYER_OFFER_STATUS_PENDING: {"label": "Активна", "css_class": "status-waiting", "priority": 10},
    CRM_OFFER_STATUS_SELECTED: {"label": "Обрано", "css_class": "status-success", "priority": 20},
    BUYER_OFFER_STATUS_ACCEPTED: {"label": "Обрано", "css_class": "status-success", "priority": 20},
    CRM_OFFER_STATUS_REJECTED: {"label": "Не обрано", "css_class": "status-rejected", "priority": 30},
    CRM_OFFER_STATUS_ALL: {"label": "Всі", "css_class": "", "priority": 40},
}


def get_crm_lead_status_meta(status: str) -> dict:
    normalized = normalize_text_status(status, CRM_LEAD_STATUS_NEW)
    return dict(_CRM_LEAD_STATUS_META.get(normalized, _CRM_LEAD_STATUS_META[CRM_LEAD_STATUS_NEW]))


def get_crm_offer_status_meta(status: str) -> dict:
    normalized = normalize_text_status(status, CRM_OFFER_STATUS_ACTIVE)
    fallback = {"label": normalized or "—", "css_class": "", "priority": 99}
    return dict(_CRM_OFFER_STATUS_META.get(normalized, fallback))


def _get_display_status_meta(
    value: object,
    active_values: set[str],
    inactive_values: set[str],
    *,
    active_label: str,
    inactive_label: str,
) -> dict:
    normalized = normalize_text_status(value, "active")
    if normalized in active_values:
        status = "active"
        is_active = True
    elif normalized in inactive_values:
        status = "inactive"
        is_active = False
    else:
        status = normalized or "active"
        is_active = status == "active"
    return {
        "status": status,
        "label": active_label if is_active else inactive_label,
        "css_class": "status-success" if is_active else "status-rejected",
        "is_active": is_active,
    }


def get_car_display_status(value: object) -> dict:
    return _get_display_status_meta(
        value,
        CAR_STATUS_ACTIVE_VALUES,
        CAR_STATUS_INACTIVE_VALUES,
        active_label="Активне",
        inactive_label="Вимкнене",
    )


def get_service_display_status(value: object) -> dict:
    return _get_display_status_meta(
        value,
        SERVICE_ACTIVE_VALUES,
        SERVICE_INACTIVE_VALUES,
        active_label="Активна",
        inactive_label="Неактивна",
    )


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
