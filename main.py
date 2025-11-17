"""
Main FastAPI application entry point.
Replaces the Flask app with modern FastAPI framework.
"""

from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import check_db_connection, get_db_info
from services.supabase import get_supabase_client_safe
from observability.logfire_config import LogfireConfig
from api.routes import user_router, email_router
import logfire


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    print("=" * 50)
    print("Starting Scribe API Server")
    print("=" * 50)
    print(f"Environment: {settings.environment}")
    print(f"Debug mode: {settings.debug}")

    # Check database connection on startup
    db_info = get_db_info()
    print(f"\nDatabase: {db_info['url']}")
    print(f"Status: {db_info['status']}")

    if db_info['status'] == 'connected':
        print("✓ Database connection successful")
    else:
        print("✗ Database connection failed!")
        print("  Please check your DATABASE_URL in .env file")

    # Check Supabase client initialization
    print("\nChecking Supabase connection...")
    supabase = get_supabase_client_safe()
    if supabase:
        print("✓ Supabase client initialized successfully")
    else:
        print("✗ Supabase client initialization failed!")
        print("  Please check your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env file")

    # Initialize Logfire observability
    print("\nInitializing Logfire observability...")
    LogfireConfig.initialize(token=settings.logfire_token)

    # Log local instance creation for development environments
    if settings.is_development:
        import logfire
        logfire.info("Local development instance created", environment=settings.environment)

    print("=" * 50)

    yield

    # Shutdown
    print("\nShutting down Scribe API Server...")


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
    allow_origins=settings.cors_origins,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
