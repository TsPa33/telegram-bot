from dataclasses import asdict, dataclass
from typing import Iterable

from fastapi import UploadFile

class RequestPhotoValidationError(ValueError):
    pass


def short_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


MAX_REQUEST_PHOTOS = 5
MAX_PHOTO_SIZE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@dataclass(slots=True)
class RequestPhotoAsset:
    filename: str | None
    content_type: str | None
    storage_status: str
    moderation_status: str
    cloudinary_public_id: str | None = None
    bytes_limit: int = MAX_PHOTO_SIZE_BYTES

    def to_dict(self) -> dict:
        return asdict(self)


def prepare_request_photo_assets(photos: Iterable[UploadFile] | None) -> list[dict]:
    assets: list[dict] = []
    for photo in photos or []:
        if not photo or not photo.filename:
            continue
        content_type = short_text(photo.content_type, 80)
        if content_type and content_type not in ALLOWED_IMAGE_TYPES and not content_type.startswith("image/"):
            raise RequestPhotoValidationError("Фото мають бути зображеннями.")
        assets.append(
            RequestPhotoAsset(
                filename=short_text(photo.filename, 180),
                content_type=content_type,
                storage_status="pending_cloudinary_upload",
                moderation_status="pending_review",
            ).to_dict()
        )
        if len(assets) >= MAX_REQUEST_PHOTOS:
            break
    return assets
