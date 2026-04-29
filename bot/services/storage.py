import os
import cloudinary
import cloudinary.uploader


cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


async def upload_image(file_path: str) -> str:
    result = cloudinary.uploader.upload(file_path)

    # 🔥 ГАРАНТОВАНО ПОВЕРТАЄМО STRING
    url = result.get("secure_url") or result.get("url")

    if not isinstance(url, str):
        raise ValueError("Cloudinary did not return a valid URL")

    return url
