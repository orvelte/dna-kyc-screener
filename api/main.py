"""FastAPI application entry point.

Start with:
    uvicorn api.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="DNA KYC Screener",
    description="Rule-based KYC screening for DNA synthesis orders.",
    version="0.1.0",
)

# Allow requests from the local file:// origin (frontend/index.html opened directly)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
