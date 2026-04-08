"""FastAPI application entry point.

Start with:
    uvicorn api.main:app --reload
"""

from fastapi import FastAPI

from api.routes import router

app = FastAPI(
    title="DNA KYC Screener",
    description="Rule-based KYC screening for DNA synthesis orders.",
    version="0.1.0",
)

app.include_router(router)
