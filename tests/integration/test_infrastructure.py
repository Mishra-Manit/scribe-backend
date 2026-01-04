"""
Infrastructure smoke test script.

Tests that all Phase 1 components are properly configured and can be imported.
Run this after setting up infrastructure to verify everything is working.

Usage:
    python tests/integration/test_infrastructure.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import settings for configuration
from config.settings import settings


def test_redis_config():
    """Test Redis configuration import and settings."""
    print("\n" + "=" * 50)
    print("Testing Redis Configuration")
    print("=" * 50)

    try:
        from config.redis_config import redis_settings

        print(f"✓ Redis config imported successfully")
        print(f"  Host: {redis_settings.redis_host}")
        print(f"  Port: {redis_settings.redis_port}")
        print(f"  DB: {redis_settings.redis_db}")
        print(f"  Broker URL: {redis_settings.broker_url}")
        print(f"  Result Backend: {redis_settings.result_backend}")

        return True
    except Exception as e:
        print(f"✗ Redis config failed: {e}")
        return False


def test_logfire_config():
    """Test Logfire configuration import."""
    print("\n" + "=" * 50)
    print("Testing Logfire Configuration")
    print("=" * 50)

    try:
        from observability.logfire_config import LogfireConfig

        print(f"✓ Logfire config imported successfully")
        print(f"  Initialized: {LogfireConfig.is_initialized()}")

        # Try to initialize with token from settings
        LogfireConfig.initialize(token=settings.logfire_token)
        print(f"  After init: {LogfireConfig.is_initialized()}")

        return True
    except Exception as e:
        print(f"✗ Logfire config failed: {e}")
        return False


def test_celery_config():
    """Test Celery configuration import."""
    print("\n" + "=" * 50)
    print("Testing Celery Configuration")
    print("=" * 50)

    try:
        from celery_config import celery_app, health_check

        print(f"✓ Celery app imported successfully")
        print(f"  App name: {celery_app.main}")
        print(f"  Broker: {celery_app.conf.broker_url}")
        print(f"  Backend: {celery_app.conf.result_backend}")
        print(f"  Task routes: {celery_app.conf.task_routes}")

        # Test health check task registration
        print(f"✓ Health check task registered: {health_check.name}")

        return True
    except Exception as e:
        print(f"✗ Celery config failed: {e}")
        return False


def test_redis_connection():
    """Test actual Redis connection (optional - requires Redis running)."""
    print("\n" + "=" * 50)
    print("Testing Redis Connection (Optional)")
    print("=" * 50)

    try:
        import redis
    except ImportError:
        print("⚠️  Redis package not installed (install with: pip install redis)")
        return None

    try:
        from config.redis_config import redis_settings

        r = redis.Redis(
            host=redis_settings.redis_host,
            port=redis_settings.redis_port,
            db=redis_settings.redis_db,
            password=redis_settings.redis_password,
            socket_connect_timeout=2
        )

        # Test ping
        r.ping()
        print("✓ Redis connection successful")
        print(f"  Redis version: {r.info()['redis_version']}")

        return True
    except redis.ConnectionError:
        print("⚠️  Redis not running (this is OK for now)")
        print("   Start Redis with: brew services start redis (macOS)")
        return None  # Not a failure, just not available
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        return False


def main():
    """Run all infrastructure tests."""
    print("\n" + "=" * 70)
    print(" " * 20 + "INFRASTRUCTURE SMOKE TEST")
    print("=" * 70)

    results = {
        "Redis Config": test_redis_config(),
        "Logfire Config": test_logfire_config(),
        "Celery Config": test_celery_config(),
        "Redis Connection": test_redis_connection(),
    }

    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    for test_name, result in results.items():
        if result is True:
            status = "✓ PASS"
        elif result is None:
            status = "⚠️  SKIP"
        else:
            status = "✗ FAIL"

        print(f"{status:10} {test_name}")

    # Determine overall status
    failures = sum(1 for r in results.values() if r is False)

    print("=" * 70)

    if failures == 0:
        print("✓ All tests passed! Infrastructure is ready.")
        print("\nNext steps:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Start Redis: brew services start redis (macOS)")
        print("  3. Update .env with actual API keys")
        print("  4. Start Celery worker: celery -A celery_config.celery_app worker --loglevel=info")
        return 0
    else:
        print(f"✗ {failures} test(s) failed. Please fix errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
