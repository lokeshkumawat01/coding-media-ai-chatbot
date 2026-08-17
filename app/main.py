"""
FastAPI application entrypoint.
Sets up CORS, rate limiting, the /health check endpoint, and includes
the chat and admin routers.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.rate_limit import limiter
from app.utils.logger import logger
from app.routes.chat import router as chat_router
from app.routes.admin import router as admin_router
from app.rag.chroma_client import get_knowledge_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info(f"Application starting in '{settings.app_env}' mode")

    # Auto-reseed knowledge base if ChromaDB is empty (happens on Render's
    # ephemeral disk after every restart/redeploy since local storage
    # doesn't persist between deploys on the free tier).
    try:
        collection = get_knowledge_collection()
        if collection.count() == 0:
            logger.info("ChromaDB collection is empty — auto-reseeding from knowledge_base/ folder")
            import sys
            sys.path.insert(0, ".")
            from scripts.load_knowledge_base import main as load_kb
            load_kb()
            logger.info(f"Auto-reseed complete. Total documents: {collection.count()}")
        else:
            logger.info(f"ChromaDB already has {collection.count()} documents — skipping reseed")
    except Exception as e:
        logger.error(f"Auto-reseed failed: {e}")

    yield  # App runs here

    # --- Shutdown ---
    logger.info("Application shutting down")


app = FastAPI(
    title="Solutions Agency Chatbot API",
    version="0.1.0",
    debug=settings.app_debug,
    lifespan=lifespan,
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