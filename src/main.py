"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from __init__ import __version__
from freemium.router import router as license_router
from testing.router import router as testing_router
from webhook.router import router as webhook_router

app = FastAPI(
    title="RunOwl",
    description="AI-powered code review and testing agent",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(license_router)
app.include_router(testing_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
