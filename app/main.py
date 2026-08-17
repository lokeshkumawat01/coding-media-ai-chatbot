"""
FastAPI application entrypoint.
Sets up CORS, rate limiting, the /health check endpoint, and includes
the chat and admin routers.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.rate_limit import limiter
from app.utils.logger import logger
from app.routes.chat import router as chat_router
from app.routes.admin import router as admin_router

app = FastAPI(
    title="Solutions Agency Chatbot API",
    version="0.1.0",
    debug=settings.app_debug,
)

# --- Rate limiting ---
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"Rate limit exceeded for IP: {request.client.host}")
    return JSONResponse(
        status_code=429,
        content={"error": "Too many requests. Please try again later."},
    )


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(chat_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


# --- Health check ---
@app.get("/health")
async def health_check():
    """
    Basic health check endpoint. Used by UptimeRobot and load balancers.
    Extend later to check DB/Redis connectivity if needed.
    """
    return {"status": "ok", "environment": settings.app_env}


@app.on_event("startup")
async def on_startup():
    logger.info(f"Application starting in '{settings.app_env}' mode")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Application shutting down")
