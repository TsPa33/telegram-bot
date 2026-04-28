# bot/services/storage.py

import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name="YOUR_CLOUD_NAME",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    secure=True
)
