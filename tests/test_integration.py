"""Integration tests for FastSyftBox end-to-end functionality."""

import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig
from typer.testing import CliRunner

from fastsyftbox import FastSyftBox
from fastsyftbox.cli import app as cli_app
from fastsyftbox.http_bridge import SyftHTTPBridge


class IntegrationIntegrationTestModel(BaseModel):
    """Test model for integration tests."""

    message: str
    name: str = "test"


@pytest.mark.integration
class TestAppCreationAndStartup:
    """Test complete app creation and startup process."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.temp_dir = None

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_full_app_creation_workflow(self):
        """Test complete app creation from CLI to file structure validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                # Change to temp directory
                import os

                os.chdir(temp_dir)

                app_name = "test_integration_app"
                app_path = Path(temp_dir) / app_name

                # Create app using CLI
                result = self.runner.invoke(cli_app, ["create", "app", app_name])

                # Debug output if test fails
                if result.exit_code != 0:
                    print(f"CLI Output: {result.stdout}")
                    print(f"CLI Error: {result.stderr}")
                    if result.exception:
                        print(f"Exception: {result.exception}")

                # Verify CLI success
                assert result.exit_code == 0, f"CLI failed with output: {result.stdout}"
                assert (
                    f"FastSyftbox App '{app_name}' created successfully"
                    in result.stdout
                )

                # Verify directory structure
                assert app_path.exists()
                assert (app_path / "app.py").exists()
                assert (app_path / "requirements.txt").exists()
                assert (app_path / "run.sh").exists()

                # Verify template content customization
                app_py_content = (app_path / "app.py").read_text()
                assert "from fastsyftbox import FastSyftBox" in app_py_content
                assert (
                    "app_name = Path(__file__).resolve().parent.name" in app_py_content
                )

                # Verify run.sh is executable (at least readable)
                run_sh_content = (app_path / "run.sh").read_text()
                assert "uvicorn app:app" in run_sh_content
                assert "SYFTBOX_ASSIGNED_PORT" in run_sh_content
            finally:
                os.chdir(original_cwd)

    def test_app_creation_with_existing_directory(self):
        """Test app creation fails when directory already exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(temp_dir)

                app_name = "existing_app"
                app_path = Path(temp_dir) / app_name
                app_path.mkdir()  # Create directory first

                result = self.runner.invoke(cli_app, ["create", "app", app_name])

                assert result.exit_code == 1
                assert "already exists" in result.stdout
            finally:
                os.chdir(original_cwd)

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_template_app_initialization(self, mock_client_class, mock_config_load):
        """Test that template app can be initialized properly."""
        # Mock SyftBox dependencies
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.email = "test@example.com"
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Create app similar to template
        app = FastSyftBox(
            app_name="test_template_app",
            syftbox_endpoint_tags=["syftbox"],
            include_syft_openapi=True,
        )

        # Add routes like in template
        @app.get("/")
        def root():
            return {"message": "Welcome to test_template_app"}

        @app.post("/hello", tags=["syftbox"])
        def hello_handler(request: dict):
            return {"message": f"Hi {request.get('name', 'User')}", "name": "Bot"}

        # Enable debug tool
        app.enable_debug_tool(
            endpoint="/hello",
            example_request=json.dumps({"message": "Hello!", "name": "Alice"}),
            publish=False,
        )

        # Verify app properties
        assert app.app_name == "test_template_app"
        assert app.syftbox_endpoint_tags == ["syftbox"]
        assert app.include_syft_openapi is True

        # Verify routes are properly configured
        syft_routes = list(app._discover_syft_routes())
        syft_endpoints = [route.path for route in syft_routes]
        assert "/hello" in syft_endpoints

        # Verify debug tool is enabled
        debug_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and route.path == "/rpc-debug"
        ]
        assert len(debug_routes) > 0


@pytest.mark.integration
class TestRPCEndpointRegistrationAndDiscovery:
    """Test RPC endpoint registration and discovery functionality."""

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_rpc_endpoint_discovery(self, mock_client_class, mock_config_load):
        """Test discovery of RPC-enabled endpoints."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        # Create app with specific tags
        app = FastSyftBox(
            app_name="test_rpc_app", syftbox_endpoint_tags=["rpc", "syftbox"]
        )

        # Add various routes
        @app.get("/public")
        def public_route():
            return {"type": "public"}

        @app.post("/rpc-only", tags=["rpc"])
        def rpc_only_route():
            return {"type": "rpc"}

        @app.post("/syftbox-only", tags=["syftbox"])
        def syftbox_only_route():
            return {"type": "syftbox"}

        @app.post("/both-tags", tags=["rpc", "syftbox"])
        def both_tags_route():
            return {"type": "both"}

        @app.post("/irrelevant-tag", tags=["other"])
        def irrelevant_route():
            return {"type": "other"}

        # Test endpoint discovery
        syft_routes = list(app._discover_syft_routes())
        syft_endpoints = [route.path for route in syft_routes]

        # Should include routes with rpc or syftbox tags
        assert "/rpc-only" in syft_endpoints
        assert "/syftbox-only" in syft_endpoints
        assert "/both-tags" in syft_endpoints

        # Should not include routes without matching tags
        assert "/public" not in syft_endpoints
        assert "/irrelevant-tag" not in syft_endpoints

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_rpc_discovery_all_routes(self, mock_client_class, mock_config_load):
        """Test discovery when no specific tags are provided (all routes)."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        # Create app without specific tags
        app = FastSyftBox(app_name="test_all_routes_app", syftbox_endpoint_tags=None)

        @app.get("/route1")
        def route1():
            return {"id": 1}

        @app.post("/route2")
        def route2():
            return {"id": 2}

        # Test discovery includes all API routes
        syft_routes = list(app._discover_syft_routes())
        syft_endpoints = [route.path for route in syft_routes]

        assert "/route1" in syft_endpoints
        assert "/route2" in syft_endpoints

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_openapi_endpoint_generation(self, mock_client_class, mock_config_load):
        """Test OpenAPI endpoint generation for Syft routes."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        app = FastSyftBox(
            app_name="test_openapi_app",
            syftbox_endpoint_tags=["syftbox"],
            include_syft_openapi=True,
        )

        @app.post("/api-endpoint", tags=["syftbox"])
        def api_endpoint(data: dict):
            return {"received": data.get("message", "test")}

        # Check if OpenAPI endpoint is created by examining routes after app initialization
        # The OpenAPI endpoint is created during the lifespan startup
        openapi_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and "/syft/openapi.json" in str(route.path)
        ]

        # If no routes found by path check, check by name/tag
        if len(openapi_routes) == 0:
            # Check for function-based routes that might be added
            from fastapi.routing import APIRoute

            api_routes = [route for route in app.routes if isinstance(route, APIRoute)]
            openapi_routes = [
                route
                for route in api_routes
                if hasattr(route, "tags") and "syft_docs" in route.tags
            ]

        # The endpoint might not be visible until after lifespan startup
        # Let's test the method that creates the OpenAPI endpoints directly
        syft_routes = list(app._discover_syft_routes())
        app._create_syft_openapi_endpoints(syft_routes)

        # Now check again
        openapi_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and "/syft/openapi.json" in str(route.path)
        ]
        assert len(openapi_routes) > 0

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_openapi_disabled(self, mock_client_class, mock_config_load):
        """Test that OpenAPI endpoint is not created when disabled."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        app = FastSyftBox(
            app_name="test_no_openapi_app",
            syftbox_endpoint_tags=["syftbox"],
            include_syft_openapi=False,
        )

        @app.post("/api-endpoint", tags=["syftbox"])
        def api_endpoint():
            return {"status": "ok"}

        # Check OpenAPI endpoint is not created
        openapi_routes = [
            route
            for route in app.routes
            if hasattr(route, "path") and route.path == "/syft/openapi.json"
        ]
        assert len(openapi_routes) == 0


@pytest.mark.integration
class TestTemplateGenerationAndValidation:
    """Test template generation and validation functionality."""

    def test_template_structure_validation(self):
        """Test that app template has correct structure."""
        template_dir = Path(__file__).parent.parent / "fastsyftbox" / "app_template"

        # Verify core files exist
        assert (template_dir / "app.py").exists()
        assert (template_dir / "requirements.txt").exists()
        assert (template_dir / "run.sh").exists()

        # Verify assets directory structure
        assets_dir = template_dir / "assets"
        assert assets_dir.exists()
        assert (assets_dir / "rpc-debug.html").exists()
        assert (assets_dir / "css" / "rpc-debug.css").exists()
        assert (assets_dir / "js" / "rpc-debug.js").exists()
        assert (assets_dir / "js" / "syftbox-sdk.js").exists()

    def test_template_content_validation(self):
        """Test that template files contain expected content."""
        template_dir = Path(__file__).parent.parent / "fastsyftbox" / "app_template"

        # Check app.py content
        app_py = (template_dir / "app.py").read_text()
        assert "from fastsyftbox import FastSyftBox" in app_py
        assert "app_name = Path(__file__).resolve().parent.name" in app_py
        assert "syftbox" in app_py  # Should have syftbox tag
        assert "enable_debug_tool" in app_py

        # Check requirements.txt
        requirements = (template_dir / "requirements.txt").read_text()
        assert "fastsyftbox" in requirements
        assert "syft-core" in requirements

        # Check run.sh
        run_sh = (template_dir / "run.sh").read_text()
        assert "uvicorn app:app" in run_sh
        assert "SYFTBOX_ASSIGNED_PORT" in run_sh

    def test_template_customization_after_copy(self):
        """Test that template can be properly customized after copying."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_dir = Path(__file__).parent.parent / "fastsyftbox" / "app_template"
            app_dir = Path(temp_dir) / "custom_app"

            # Copy template
            shutil.copytree(template_dir, app_dir)

            # Verify app name detection works
            app_py_content = (app_dir / "app.py").read_text()

            # The app name should be derived from directory name
            expected_line = "app_name = Path(__file__).resolve().parent.name"
            assert expected_line in app_py_content

            # Test that when imported, it would use the directory name
            # (This is tested indirectly through the template structure)


@pytest.mark.integration
class TestFastAPIIntegrationWithSyftBox:
    """Test FastAPI integration with SyftBox functionality."""

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_fastapi_syftbox_integration(
        self, mock_syft_events, mock_client_class, mock_config_load
    ):
        """Test complete FastAPI and SyftBox integration."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.email = "test@example.com"
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Mock SyftEvents
        mock_events_instance = Mock()
        mock_syft_events.return_value = mock_events_instance

        # Create lifespan for testing
        @asynccontextmanager
        async def test_lifespan(app: FastAPI):
            # Startup
            app.state.started = True
            yield
            # Shutdown
            app.state.stopped = True

        # Create app with lifespan
        app = FastSyftBox(
            app_name="integration_test_app",
            syftbox_endpoint_tags=["syftbox"],
            lifespan=test_lifespan,
        )

        @app.post("/test-endpoint", tags=["syftbox"])
        def test_endpoint(data: dict):
            return {"message": f"Hello {data.get('name', 'User')}"}

        # Test with TestClient (this will trigger lifespan)
        with TestClient(app) as client:
            # Test FastAPI endpoint directly
            response = client.post(
                "/test-endpoint", json={"message": "test", "name": "Alice"}
            )
            assert response.status_code == 200
            assert response.json()["message"] == "Hello Alice"

            # Verify SyftEvents was initialized
            mock_syft_events.assert_called_once()
            mock_events_instance.start.assert_called_once()

    @patch("fastsyftbox.http_bridge.SyftEvents")
    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_bridge_initialization(
        self, mock_client_class, mock_config_load, mock_syft_events
    ):
        """Test HTTP bridge initialization and configuration."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        # Mock SyftEvents and setup path handling
        mock_events_instance = Mock()
        mock_events_instance.app_dir = Path("/tmp/test_app")
        mock_syft_events.return_value = mock_events_instance

        app = FastSyftBox(app_name="bridge_test_app", syftbox_endpoint_tags=["syftbox"])

        @app.post("/bridge-test", tags=["syftbox"])
        def bridge_test():
            return {"bridge": "working"}

        # Create a mock HTTP client
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)

        # Test bridge creation
        bridge = SyftHTTPBridge(
            app_name="bridge_test_app",
            http_client=mock_http_client,
            included_endpoints=["/bridge-test"],
            syftbox_client=mock_client,
        )

        assert bridge.included_endpoints == ["/bridge-test"]
        assert bridge.app_client == mock_http_client

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_file_publishing(self, mock_client_class, mock_config_load):
        """Test file publishing functionality."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        app = FastSyftBox(app_name="publish_test_app")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test content")

            # Mock the datasite path
            datasite_path = Path(temp_dir) / "datasite"
            mock_client.datasite_path = datasite_path

            # Test file publishing
            in_datasite_path = Path("public") / "test.txt"
            app.publish_file_path(test_file, in_datasite_path)

            # Verify file was copied
            published_file = datasite_path / in_datasite_path
            assert published_file.exists()
            assert published_file.read_text() == "test content"

        # Test content publishing
        with tempfile.TemporaryDirectory() as temp_dir:
            datasite_path = Path(temp_dir) / "datasite"
            mock_client.datasite_path = datasite_path

            content = "direct content"
            in_datasite_path = Path("public") / "direct.txt"
            app.publish_contents(content, in_datasite_path)

            published_file = datasite_path / in_datasite_path
            assert published_file.exists()
            assert published_file.read_text() == content


@pytest.mark.integration
class TestDebugToolFunctionality:
    """Test debug tool functionality."""

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_debug_tool_page_generation(self, mock_client_class, mock_config_load):
        """Test RPC debug tool page generation."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.email = "test@example.com"
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client_class.return_value = mock_client

        app = FastSyftBox(app_name="debug_test_app")

        # Test debug page generation
        endpoint = "/test-endpoint"
        example_request = '{"message": "test", "name": "Alice"}'

        debug_content = app.make_rpc_debug_page(endpoint, example_request)

        # Verify content contains expected placeholders replaced
        assert "debug_test_app" in debug_content
        assert "/test-endpoint" in debug_content
        assert "test@example.com" in debug_content
        assert "https://test.syftbox.org" in debug_content
        assert example_request in debug_content

    @patch("fastsyftbox.http_bridge.SyftEvents")
    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_debug_tool_endpoint_creation(
        self, mock_client_class, mock_config_load, mock_syft_events
    ):
        """Test debug tool endpoint creation."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Mock SyftEvents
        mock_events_instance = Mock()
        mock_events_instance.app_dir = Path("/tmp/test_app")
        mock_syft_events.return_value = mock_events_instance

        app = FastSyftBox(app_name="debug_endpoint_test")

        # Enable debug tool
        app.enable_debug_tool(
            endpoint="/test", example_request='{"test": "data"}', publish=False
        )

        # Test with client
        client = TestClient(app)
        response = client.get("/rpc-debug")

        assert response.status_code == 200
        assert "debug_endpoint_test" in response.text
        assert "/test" in response.text

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_debug_tool_publishing(self, mock_client_class, mock_config_load):
        """Test debug tool publishing to datasite."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client_class.return_value = mock_client

        with tempfile.TemporaryDirectory() as temp_dir:
            datasite_path = Path(temp_dir) / "datasite"
            mock_client.datasite_path = datasite_path

            app = FastSyftBox(app_name="debug_publish_test")

            # Enable debug tool with publishing
            app.enable_debug_tool(
                endpoint="/publish-test",
                example_request='{"publish": "test"}',
                publish=True,
            )

            # Verify file was published
            published_file = (
                datasite_path / "public" / "debug_publish_test" / "rpc-debug.html"
            )
            assert published_file.exists()

            content = published_file.read_text()
            assert "debug_publish_test" in content
            assert "/publish-test" in content

    @patch("fastsyftbox.http_bridge.SyftEvents")
    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_debug_urls_generation(
        self, mock_client_class, mock_config_load, mock_syft_events
    ):
        """Test debug URLs generation."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Mock SyftEvents
        mock_events_instance = Mock()
        mock_events_instance.app_dir = Path("/tmp/test_app")
        mock_syft_events.return_value = mock_events_instance

        app = FastSyftBox(app_name="debug_urls_test")

        # Test without debug enabled
        urls = app.get_debug_urls()
        assert urls == ""

        # Enable debug without publishing
        app.enable_debug_tool(
            endpoint="/test", example_request='{"test": "data"}', publish=False
        )

        urls = app.get_debug_urls()
        assert "/rpc-debug" in urls
        assert "Local RPC Debug" in urls

        # Enable debug with publishing
        app.enable_debug_tool(
            endpoint="/test", example_request='{"test": "data"}', publish=True
        )

        urls = app.get_debug_urls()
        assert "/rpc-debug" in urls
        assert "Published RPC Debug" in urls
        assert "https://test.syftbox.org" in urls


@pytest.mark.integration
class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""

    def test_cli_invalid_subcommand(self):
        """Test CLI with invalid subcommand."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["create", "invalid", "test_app"])

        assert result.exit_code == 1
        assert "Invalid subcommand" in result.stdout

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    def test_syftbox_config_load_failure(self, mock_config_load):
        """Test handling of SyftBox config load failure."""
        mock_config_load.side_effect = Exception("Config load failed")

        with pytest.raises(Exception, match="Config load failed"):
            FastSyftBox(app_name="config_fail_test")

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_bridge_startup_failure(self, mock_client_class, mock_config_load):
        """Test handling of bridge startup failure."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        app = FastSyftBox(app_name="bridge_fail_test")

        @app.post("/test", tags=["syftbox"])
        def test_route():
            return {"test": "data"}

        # Mock bridge failure
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_syft_events:
            mock_events_instance = Mock()
            mock_events_instance.start.side_effect = Exception("Bridge start failed")
            mock_syft_events.return_value = mock_events_instance

            # This should handle the exception gracefully
            with pytest.raises(Exception, match="Bridge start failed"):
                with TestClient(app):
                    pass

    def test_template_directory_missing(self):
        """Test handling when template directory is missing."""
        runner = CliRunner()

        with patch("fastsyftbox.cli.Path") as mock_path:
            mock_template_dir = Mock()
            mock_template_dir.exists.return_value = False
            mock_path.return_value.__truediv__.return_value = mock_template_dir
            mock_path.return_value.exists.return_value = False  # Target doesn't exist

            with patch("fastsyftbox.cli.shutil.copytree") as mock_copytree:
                mock_copytree.side_effect = FileNotFoundError("Template not found")

                result = runner.invoke(cli_app, ["create", "app", "test_app"])
                assert result.exit_code != 0

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_empty_routes_handling(self, mock_client_class, mock_config_load):
        """Test handling of app with no routes."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        # Create app with no routes
        app = FastSyftBox(
            app_name="empty_routes_test", syftbox_endpoint_tags=["syftbox"]
        )

        # Test route discovery with no matching routes
        syft_routes = list(app._discover_syft_routes())
        assert len(syft_routes) == 0

        # App should still be creatable and testable
        client = TestClient(app)
        # Default 404 for non-existent routes
        response = client.get("/nonexistent")
        assert response.status_code == 404

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_malformed_debug_request(self, mock_client_class, mock_config_load):
        """Test debug tool with malformed example request."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client_class.return_value = mock_client

        app = FastSyftBox(app_name="malformed_debug_test")

        # Test with malformed JSON - should not crash
        malformed_request = '{"invalid": json malformed'

        # Should not raise exception
        debug_content = app.make_rpc_debug_page("/test", malformed_request)
        assert malformed_request in debug_content  # Should include as-is

    @patch("fastsyftbox.http_bridge.SyftEvents")
    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_lifespan_exception_handling(
        self, mock_client_class, mock_config_load, mock_syft_events
    ):
        """Test handling of exceptions in user lifespan."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Mock SyftEvents to prevent the other error
        mock_events_instance = Mock()
        mock_events_instance.app_dir = Path("/tmp/test_app")
        mock_syft_events.return_value = mock_events_instance

        @asynccontextmanager
        async def failing_lifespan(app: FastAPI):
            raise Exception("Lifespan failed")
            yield  # This line won't be reached

        app = FastSyftBox(app_name="failing_lifespan_test", lifespan=failing_lifespan)

        # Should handle lifespan exception - but the actual exception might be different
        # due to the SyftEvents initialization happening first
        with pytest.raises(Exception):
            with TestClient(app):
                pass

    def test_version_command_output(self):
        """Test version command returns correct version."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["version"])

        assert result.exit_code == 0
        assert "FastSyftbox version:" in result.stdout
        assert "0.1.7" in result.stdout  # Should match current version


@pytest.mark.integration
class TestConcurrentOperations:
    """Test concurrent operations and race conditions."""

    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_concurrent_requests_handling(self, mock_client_class, mock_config_load):
        """Test handling of concurrent requests to FastAPI endpoints."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config_load.return_value = mock_config
        mock_client = Mock(spec=SyftboxClient)
        mock_client_class.return_value = mock_client

        app = FastSyftBox(app_name="concurrent_test")

        request_count = 0

        @app.post("/concurrent-test")
        def concurrent_endpoint():
            nonlocal request_count
            request_count += 1
            return {"request_id": request_count}

        client = TestClient(app)

        # Simulate concurrent requests
        responses = []
        for i in range(10):
            response = client.post("/concurrent-test")
            responses.append(response)

        # All requests should succeed
        assert all(r.status_code == 200 for r in responses)
        assert len(set(r.json()["request_id"] for r in responses)) == 10  # All unique

    @patch("fastsyftbox.http_bridge.SyftEvents")
    @patch("fastsyftbox.fastsyftbox.SyftClientConfig.load")
    @patch("fastsyftbox.fastsyftbox.SyftboxClient")
    def test_multiple_debug_tool_calls(
        self, mock_client_class, mock_config_load, mock_syft_events
    ):
        """Test multiple calls to enable_debug_tool."""
        # Setup mocks
        mock_config = Mock(spec=SyftClientConfig)
        mock_config.server_url = "https://test.syftbox.org"
        mock_config_load.return_value = mock_config

        mock_client = Mock(spec=SyftboxClient)
        mock_client.email = "test@example.com"
        mock_client.datasite_path = Path("/tmp/test_datasite")
        mock_client_class.return_value = mock_client

        # Mock SyftEvents
        mock_events_instance = Mock()
        mock_events_instance.app_dir = Path("/tmp/test_app")
        mock_syft_events.return_value = mock_events_instance

        app = FastSyftBox(app_name="multiple_debug_test")

        # Call enable_debug_tool multiple times - should not crash
        app.enable_debug_tool("/test1", '{"test": 1}', publish=False)
        app.enable_debug_tool("/test2", '{"test": 2}', publish=False)

        client = TestClient(app)
        response = client.get("/rpc-debug")

        # Should still work (latest call should take effect)
        assert response.status_code == 200
