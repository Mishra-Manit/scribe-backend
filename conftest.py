"""Root conftest.py for pytest configuration.

This file configures pytest for the entire project, ensuring:
- Proper Python path setup for imports
- Logfire observability configuration
- Shared fixtures across all tests
- Async test support
"""

import sys
from pathlib import Path

import logfire
import pytest


# ============================================================================
# Python Path Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings and ensure project root is in sys.path."""

    # Add project root to sys.path to ensure 'pipeline' package is importable
    project_root = Path(__file__).parent.resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Register custom markers
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests requiring external services"
    )
    config.addinivalue_line(
        "markers",
        "unit: marks tests as unit tests (fast, no external dependencies)"
    )

    # Configure logfire for all tests
    logfire.configure(
        service_name="pythonserver_tests",
        environment="test",
        send_to_logfire=True,  # Send test logs to remote server for debugging
    )

    # Ensure pydantic-ai agents emit detailed spans (inputs/outputs) in tests
    logfire.instrument_pydantic_ai()

    logfire.info(
        "Starting test suite",
        project_root=str(project_root),
        python_path=sys.path[:3],  # Log first 3 paths for debugging
    )


def pytest_sessionfinish(session, exitstatus):
    """Log test session completion with summary statistics."""
    logfire.info(
        "Test suite completed",
        exit_status=exitstatus,
        tests_collected=session.testscollected,
        tests_failed=session.testsfailed,
        duration=session.testscollected,
    )


# ============================================================================
# Shared Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def project_root():
    """Return the absolute path to the project root directory."""
    return Path(__file__).parent.resolve()


@pytest.fixture(scope="session")
def pipeline_root(project_root):
    """Return the absolute path to the pipeline package directory."""
    return project_root / "pipeline"


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Fixture to mock environment variables for testing.

    Usage:
        def test_something(mock_env_vars):
            mock_env_vars({"API_KEY": "test-key", "DEBUG": "true"})
    """
    def _set_env_vars(env_dict: dict):
        for key, value in env_dict.items():
            monkeypatch.setenv(key, value)

    return _set_env_vars


# ============================================================================
# Async Test Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """Set the event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


# ============================================================================
# Database Fixtures (for future use)
# ============================================================================

# Uncomment when database tests are needed
# @pytest.fixture(scope="function")
# async def test_db():
#     """Create a test database session."""
#     # TODO: Implement test database setup/teardown
#     pass
