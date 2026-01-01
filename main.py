"""
Main FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logfire

from config import settings
from database import check_db_connection, get_db_info
from services.supabase import get_supabase_client_safe
from observability.logfire_config import LogfireConfig
from api.routes import user_router, email_router, template_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Initialize Logfire first so we can use structured logging
    LogfireConfig.initialize(token=settings.logfire_token)

    # Startup logging
    logfire.info(
        "Starting Scribe API Server",
        environment=settings.environment,
        debug=settings.debug,
    )

    # Check database connection on startup
    db_info = get_db_info()
    if db_info['status'] == 'connected':
        logfire.info(
            "Database connection successful",
            url=db_info['url'],
            status=db_info['status'],
        )
    else:
        logfire.error(
            "Database connection failed",
            url=db_info['url'],
            status=db_info['status'],
        )

    # Check Supabase client initialization
    supabase = get_supabase_client_safe()
    if supabase:
        logfire.info("Supabase client initialized successfully")
    else:
        logfire.error(
            "Supabase client initialization failed",
            hint="Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env file",
        )

    # Validate CORS configuration
    logfire.info(
        "CORS configuration",
        allowed_origins=settings.allowed_origins,
        origin_count=len(settings.allowed_origins),
        environment=settings.environment,
    )

    # Warn about potential CORS issues
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

    # Shutdown
    logfire.info("Shutting down Scribe API Server")


# Initialize FastAPI app
app = FastAPI(
    title="Scribe API",
    description="Backend API for Scribe - Cold email generation platform",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for load balancers and monitoring.

    Returns:
        dict: Health status of the application and database
    """
    db_connected = check_db_connection()

    return {
        "status": "healthy" if db_connected else "degraded",
        "service": "scribe-api",
        "version": "1.0.0",
        "database": "connected" if db_connected else "disconnected",
        "environment": settings.environment,
    }


@app.get("/debug/cors", tags=["Health"])
async def debug_cors() -> Dict:
    """
    Debug endpoint to verify CORS configuration.

    Returns current CORS settings for troubleshooting.
    Remove this endpoint in production or add authentication.
    """
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
    """
    Root endpoint - API information.

    Returns:
        dict: Basic API information
    """
    return {
        "name": "Scribe API",
        "version": "1.0.0",
        "description": "Backend API for cold email generation",
        "docs": "/docs",
        "health": "/health",
    }


# ============================================================================
# API Routers
# ============================================================================

# User management endpoints (authentication required)
app.include_router(user_router)

# Email generation endpoints (authentication required, uses Celery workers)
app.include_router(email_router)

# Template generation endpoints (authentication required, synchronous)
app.include_router(template_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
