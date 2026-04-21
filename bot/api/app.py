from fastapi import FastAPI
from bot.api.liqpay_callback import router as liqpay_router

app = FastAPI()

app.include_router(liqpay_router)
