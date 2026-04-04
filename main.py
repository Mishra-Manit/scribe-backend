"""
Main FastAPI application entry point.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logfire

from config import settings
from database import check_db_connection, get_db_info
from services.supabase import get_supabase_client_safe
from observability.logfire_config import LogfireConfig
from api.routes import user_router, email_router, template_router, queue_router, admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    LogfireConfig.initialize(token=settings.logfire_token)

    logfire.info(
        "Starting Scribe API Server",
        environment=settings.environment,
        debug=settings.debug,
    )

    logfire.info(
        "Database configuration",
        port=settings.db_port,
        host_type="transaction_pooler" if ".pooler." in settings.db_host else "direct",
        pool_class="NullPool",
        connect_timeout=settings.db_connect_timeout,
    )

    async def check_db_with_logging():
        db_info = get_db_info()
        if db_info["status"] == "connected":
            logfire.info(
                "Database connection successful",
                url=db_info["url"],
                port=settings.db_port,
                status=db_info["status"],
            )
        else:
            from sqlalchemy.exc import OperationalError

            error_msg = db_info.get("error", "Connection check failed")
            logfire.warning(
                "Database connection check failed",
                url=db_info["url"],
                port=settings.db_port,
                status=db_info["status"],
                error=error_msg,
            )
            raise OperationalError(
                statement=None, params=None, orig=Exception(error_msg)
            )
        return db_info

    from database import retry_on_db_error_async

    try:
        db_info = await retry_on_db_error_async(check_db_with_logging)
    except Exception as e:
        logfire.error(
            "Database connection failed after retries",
            error=str(e),
            port=settings.db_port,
        )
        db_info = None

    supabase = get_supabase_client_safe()
    if supabase:
        logfire.info("Supabase client initialized successfully")
    else:
        logfire.error(
            "Supabase client initialization failed",
            hint="Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env file",
        )

    logfire.info(
        "CORS configuration",
        allowed_origins=settings.allowed_origins,
        origin_count=len(settings.allowed_origins),
        environment=settings.environment,
    )

    for origin in settings.allowed_origins:
        if origin == "*":
            if settings.is_production:
                logfire.error(
                    "SECURITY WARNING: Wildcard CORS origin in production",
                    hint="Set ALLOWED_ORIGINS to specific domain in production"
                )
            continue

        if not origin.startswith(("http://", "https://")):
            logfire.error(
                "Invalid CORS origin - missing protocol",
                origin=origin,
                hint=f"Should be 'https://{origin}' or 'http://{origin}'"
            )

        if origin.endswith("/"):
            logfire.warning(
                "CORS origin has trailing slash",
                origin=origin,
                hint="Remove trailing slash for exact matching"
            )

    logfire.info("Scribe API Server startup complete")

    yield

    logfire.info("Shutting down Scribe API Server")


app = FastAPI(
    title="Scribe API",
    description="Backend API for Scribe - Cold email generation platform",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint for load balancers and monitoring."""
    db_connected = check_db_connection()

    return {
        "status": "healthy" if db_connected else "degraded",
        "service": "scribe-api",
        "version": "1.0.0",
        "database": "connected" if db_connected else "disconnected",
        "environment": settings.environment,
    }


if settings.is_development:
    @app.get("/debug/cors", tags=["Health"])
    async def debug_cors() -> Dict:
        """Debug endpoint to verify CORS configuration (development only)."""
        return {
            "allowed_origins": settings.allowed_origins,
            "origin_count": len(settings.allowed_origins),
            "is_wildcard": "*" in settings.allowed_origins,
            "environment": settings.environment,
            "credentials_enabled": True,
            "warning": "Wildcard origins violate CORS spec with credentials=True" if "*" in settings.allowed_origins else None,
        }


@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    return {
        "name": "Scribe API",
        "version": "1.0.0",
        "description": "Backend API for cold email generation",
        "docs": "/docs",
        "health": "/health",
    }


app.include_router(user_router)
app.include_router(email_router)
app.include_router(template_router)
app.include_router(queue_router)
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
