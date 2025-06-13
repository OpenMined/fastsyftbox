"""Pytest configuration and fixtures for FastSyftBox tests."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig
from syft_core.workspace import SyftWorkspace

from fastsyftbox import FastSyftBox


# Test markers setup
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that test individual components in isolation"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that test component interactions"
    )
    config.addinivalue_line(
        "markers",
        "performance: Performance tests that measure execution speed and resource usage",
    )
    config.addinivalue_line("markers", "slow: Tests that take a long time to run")
    config.addinivalue_line("markers", "network: Tests that require network access")
    config.addinivalue_line(
        "markers", "external: Tests that depend on external services"
    )
    config.addinivalue_line(
        "markers", "smoke: Quick smoke tests to verify basic functionality"
    )
    config.addinivalue_line("markers", "regression: Tests for previously found bugs")
    config.addinivalue_line("markers", "api: Tests for API endpoints")
    config.addinivalue_line("markers", "cli: Tests for command line interface")
    config.addinivalue_line(
        "markers", "auth: Tests for authentication and authorization"
    )
    config.addinivalue_line("markers", "config: Tests for configuration handling")


# Fixtures for event loop and async testing
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Auto-mocking fixtures for test isolation
@pytest.fixture(autouse=True)
def auto_mock_syft_components():
    """Automatically mock SyftBox components for all tests to ensure isolation."""
    # Mock SyftClientConfig.load() to prevent real config loading
    with patch("syft_core.config.SyftClientConfig.load") as mock_config_load:
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.email = "test@example.com"
        mock_config.data_dir = Path("/tmp/test_syftbox_data")
        mock_config.server_url = "https://test.syftbox.org"
        mock_config.client_url = "http://127.0.0.1:8080"
        mock_config.access_token = "test_token"
        mock_config.token = None
        mock_config.path = Path("/tmp/test_config.json")
        mock_config_load.return_value = mock_config

        # Mock SyftWorkspace creation
        with patch("syft_core.workspace.SyftWorkspace") as mock_workspace_class:
            mock_workspace = Mock(spec=SyftWorkspace)
            mock_workspace.data_dir = mock_config.data_dir
            mock_workspace.datasites = mock_config.data_dir / "datasites"
            mock_workspace.plugins = mock_config.data_dir / "plugins"
            mock_workspace.apps = mock_config.data_dir / "apis"
            mock_workspace_class.return_value = mock_workspace

            # Mock SyftboxClient to prevent real client creation
            with patch("fastsyftbox.fastsyftbox.SyftboxClient") as mock_client_class:
                mock_client = Mock(spec=SyftboxClient)
                mock_client.config = mock_config
                mock_client.workspace = mock_workspace
                mock_client.email = mock_config.email
                mock_client.config_path = mock_config.path
                mock_client.datasite_path = (
                    mock_config.data_dir / "datasites" / mock_config.email
                )
                mock_client.my_datasite = (
                    mock_config.data_dir / "datasites" / mock_config.email
                )
                mock_client.datasites = mock_config.data_dir / "datasites"
                mock_client.sync_folder = mock_config.data_dir / "datasites"
                mock_client_class.return_value = mock_client

                # Mock SyftEvents to prevent real event system initialization
                with patch(
                    "fastsyftbox.http_bridge.SyftEvents"
                ) as mock_syft_events_class:
                    mock_syft_events = Mock()
                    mock_syft_events.start = Mock()
                    mock_syft_events.stop = Mock()
                    mock_syft_events.on_request = Mock()
                    mock_syft_events_class.return_value = mock_syft_events

                    yield


# Configuration fixtures
@pytest.fixture
def mock_syft_config():
    """Mock SyftBox configuration for testing."""
    config = Mock(spec=SyftClientConfig)

    # Required config attributes based on SyftClientConfig
    config.email = "test@example.com"
    config.data_dir = Path("/tmp/test_syftbox_data")
    config.server_url = "https://test.syftbox.org"
    config.client_url = "http://127.0.0.1:8080"
    config.access_token = "test_token"
    config.token = None  # Deprecated field
    config.path = Path("/tmp/test_config.json")

    # Legacy attributes that might be referenced
    config.name = "Test User"

    return config


@pytest.fixture
def test_config_dict() -> Dict[str, Any]:
    """Test configuration as dictionary."""
    return {
        "email": "test@example.com",
        "name": "Test User",
        "token": None,
        "access_token": "test_token",
        "server_url": "https://test.syftbox.org",
        "client_url": "http://127.0.0.1:8080",
        "data_dir": "/tmp/test_syftbox_data",
    }


# Application fixtures
@pytest.fixture
def test_app(mock_syft_config):
    """Create a test FastSyftBox application."""
    # Auto-mocking handles the SyftboxClient and SyftWorkspace mocking
    app = FastSyftBox(
        app_name="test_app",
        syftbox_config=mock_syft_config,
        syftbox_endpoint_tags=["test"],
    )
    return app


@pytest.fixture
def test_app_with_routes(test_app):
    """Create a test app with some predefined routes."""

    @test_app.get("/health", tags=["test"])
    async def health_check():
        return {"status": "healthy"}

    @test_app.post("/echo", tags=["test"])
    async def echo_data(data: dict):
        return {"echo": data}

    @test_app.get("/config", tags=["test"])
    async def get_config():
        return {"config": "test_config"}

    return test_app


# Client fixtures
@pytest.fixture
def mock_syft_client(mock_syft_config):
    """Mock SyftBox client for testing."""
    from syft_core import Client as SyftboxClient

    client = Mock(spec=SyftboxClient)

    # Required client attributes based on Client class
    client.config = mock_syft_config
    client.email = mock_syft_config.email
    client.config_path = mock_syft_config.path
    client.my_datasite = (
        mock_syft_config.data_dir / "datasites" / mock_syft_config.email
    )
    client.datasites = mock_syft_config.data_dir / "datasites"
    client.sync_folder = mock_syft_config.data_dir / "datasites"  # Deprecated property
    client.datasite_path = (
        mock_syft_config.data_dir / "datasites" / mock_syft_config.email
    )  # Deprecated property

    # Mock workspace
    mock_workspace = Mock()
    mock_workspace.data_dir = mock_syft_config.data_dir
    mock_workspace.datasites = mock_syft_config.data_dir / "datasites"
    mock_workspace.plugins = mock_syft_config.data_dir / "plugins"
    mock_workspace.apps = mock_syft_config.data_dir / "apis"
    client.workspace = mock_workspace

    # Legacy attributes for backward compatibility
    client.api = Mock()
    client.me = Mock()
    client.me.email = mock_syft_config.email
    client.me.name = "Test User"

    return client


@pytest.fixture
def async_mock_syft_client():
    """Async mock SyftBox client for testing."""
    client = AsyncMock()
    client.api = AsyncMock()
    client.me = AsyncMock()
    client.me.email = "test@example.com"
    client.me.name = "Test User"
    return client


# HTTP Bridge fixtures
@pytest.fixture
def mock_http_bridge(mock_syft_client):
    """Mock HTTP bridge for testing."""
    from fastsyftbox.http_bridge import SyftHTTPBridge

    # Create mock HTTP client
    mock_http_client = AsyncMock()

    bridge = SyftHTTPBridge(
        app_name="test_app",
        http_client=mock_http_client,
        included_endpoints=["/test", "/echo"],
        syftbox_client=mock_syft_client,
    )
    return bridge


# File system fixtures
@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def test_data_dir(temp_dir) -> Path:
    """Create a test data directory structure."""
    data_dir = temp_dir / "test_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create some test files
    (data_dir / "test_file.txt").write_text("test content")
    (data_dir / "config.json").write_text('{"test": "config"}')

    return data_dir


# Network fixtures
@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for testing."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        yield mock_instance


# Performance fixtures
@pytest.fixture
def benchmark_config():
    """Configuration for performance benchmarks."""
    return {
        "min_rounds": 5,
        "max_time": 1.0,
        "disable_gc": True,
        "timer": "time.perf_counter",
    }


# Test data fixtures
@pytest.fixture
def sample_request_data():
    """Sample request data for testing."""
    return {
        "message": "Hello, World!",
        "timestamp": "2024-01-01T00:00:00Z",
        "user_id": "test-user-123",
        "data": {"key": "value", "number": 42},
    }


@pytest.fixture
def sample_response_data():
    """Sample response data for testing."""
    return {
        "status": "success",
        "message": "Request processed successfully",
        "data": {"result": "processed"},
        "timestamp": "2024-01-01T00:00:01Z",
    }


# CLI fixtures
@pytest.fixture
def mock_cli_args():
    """Mock CLI arguments for testing."""
    return Mock(
        port=8000,
        host="localhost",
        debug=False,
        app_name="test_app",
        config_path=None,
        log_level="INFO",
    )


# Authentication fixtures
@pytest.fixture
def mock_auth_token():
    """Mock authentication token."""
    return (
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0QGV4YW1wbGUuY29tIn0.test"
    )


@pytest.fixture
def mock_auth_headers(mock_auth_token):
    """Mock authentication headers."""
    return {
        "Authorization": f"Bearer {mock_auth_token}",
        "Content-Type": "application/json",
    }


# Utility fixtures
@pytest.fixture
def caplog_debug(caplog):
    """Capture logs at DEBUG level."""
    import logging

    caplog.set_level(logging.DEBUG)
    return caplog


# Pytest plugins and hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names and paths."""
    for item in items:
        # Add markers based on test file names
        if "test_cli" in item.fspath.basename:
            item.add_marker(pytest.mark.cli)
        elif "test_http_bridge" in item.fspath.basename:
            item.add_marker(pytest.mark.api)
        elif "test_fastsyftbox" in item.fspath.basename:
            item.add_marker(pytest.mark.unit)

        # Add markers based on test function names
        if "test_performance" in item.name or "benchmark" in item.name:
            item.add_marker(pytest.mark.performance)
        elif "test_integration" in item.name:
            item.add_marker(pytest.mark.integration)
        elif "test_smoke" in item.name:
            item.add_marker(pytest.mark.smoke)
        elif "slow" in item.name:
            item.add_marker(pytest.mark.slow)
        elif "network" in item.name:
            item.add_marker(pytest.mark.network)
        else:
            # Default to unit test marker
            item.add_marker(pytest.mark.unit)


def pytest_runtest_setup(item):
    """Setup for each test run."""
    # Skip network tests if not explicitly requested
    if item.get_closest_marker("network") and not item.config.getoption(
        "--run-network"
    ):
        pytest.skip("Network tests skipped (use --run-network to enable)")

    # Skip external tests if not explicitly requested
    if item.get_closest_marker("external") and not item.config.getoption(
        "--run-external"
    ):
        pytest.skip("External tests skipped (use --run-external to enable)")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests that require network access",
    )
    parser.addoption(
        "--run-external",
        action="store_true",
        default=False,
        help="Run tests that depend on external services",
    )
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="Run slow tests"
    )
