import cloudinary
import cloudinary.uploader


cloudinary.config(
    cloud_name="YOUR_CLOUD_NAME",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    secure=True
)


async def upload_image(file_path: str) -> str:
    result = cloudinary.uploader.upload(file_path)
    return result["secure_url"]
