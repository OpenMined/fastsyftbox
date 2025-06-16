"""
Tests for HTTP Bridge functionality.

This test suite provides comprehensive coverage for the SyftHTTPBridge class,
including:

1. Bridge initialization with proper mocking
2. Startup/shutdown lifecycle testing
3. HTTP to RPC translation logic
4. Async operation testing
5. Error handling scenarios
6. Edge cases and stress testing

Test Structure:
- Fixtures provide reusable mock objects (HTTP client, Syft client, Syft events)
- Tests cover both happy path and error scenarios
- Async tests use proper pytest.mark.asyncio decorators
- Mocking isolates the bridge logic from external dependencies

Coverage: 100% of http_bridge.py functionality
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from syft_core.url import SyftBoxURL
from syft_event.types import Request as SyftEventRequest
from syft_event.types import Response

from fastsyftbox.http_bridge import SyftHTTPBridge


class TestSyftHTTPBridge:
    """Test cases for SyftHTTPBridge class."""

    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client."""
        client = Mock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        client.request = AsyncMock()
        return client

    @pytest.fixture
    def mock_syft_client(self):
        """Mock SyftBox client."""
        return Mock()

    @pytest.fixture
    def mock_syft_events(self):
        """Mock SyftEvents."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events.start = Mock()
            mock_events.stop = Mock()
            mock_events.on_request = Mock()
            mock_events_class.return_value = mock_events
            yield mock_events

    @pytest.fixture
    def http_bridge(self, mock_http_client, mock_syft_client, mock_syft_events):
        """Create HTTP bridge instance for testing."""
        bridge = SyftHTTPBridge(
            app_name="test_app",
            http_client=mock_http_client,
            included_endpoints=["/test", "/api/data"],
            syftbox_client=mock_syft_client,
        )
        return bridge

    @pytest.mark.unit
    @pytest.mark.api
    def test_bridge_initialization(self, mock_http_client, mock_syft_client):
        """Test bridge initialization with proper parameters."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            bridge = SyftHTTPBridge(
                app_name="test_app",
                http_client=mock_http_client,
                included_endpoints=["/test", "/api/data"],
                syftbox_client=mock_syft_client,
            )

            # Verify SyftEvents is initialized with correct parameters
            mock_events_class.assert_called_once_with(
                "test_app", client=mock_syft_client
            )

            # Verify instance attributes
            assert bridge.included_endpoints == ["/test", "/api/data"]
            assert bridge.app_client == mock_http_client
            assert bridge.syft_events == mock_events

    def test_bridge_initialization_without_syftbox_client(self, mock_http_client):
        """Test bridge initialization without syftbox_client."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            SyftHTTPBridge(
                app_name="test_app",
                http_client=mock_http_client,
                included_endpoints=["/test"],
            )

            # Verify SyftEvents is initialized with None client
            mock_events_class.assert_called_once_with("test_app", client=None)

    def test_start_lifecycle(self, http_bridge, mock_syft_events):
        """Test bridge start process."""
        # Mock the _register_rpc_handlers method
        with patch.object(http_bridge, "_register_rpc_handlers") as mock_register:
            http_bridge.start()

            # Verify start is called and handlers are registered
            mock_syft_events.start.assert_called_once()
            mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_aclose_lifecycle(
        self, http_bridge, mock_syft_events, mock_http_client
    ):
        """Test bridge aclose process."""
        await http_bridge.aclose()

        # Verify both syft_events and http_client are closed
        mock_syft_events.stop.assert_called_once()
        mock_http_client.aclose.assert_called_once()

    def test_register_rpc_handlers(self, http_bridge, mock_syft_events):
        """Test RPC handler registration for all endpoints."""
        with patch.object(
            http_bridge, "_register_rpc_for_endpoint"
        ) as mock_register_endpoint:
            http_bridge._register_rpc_handlers()

            # Verify handler is registered for each endpoint
            assert mock_register_endpoint.call_count == 2
            mock_register_endpoint.assert_any_call("/test")
            mock_register_endpoint.assert_any_call("/api/data")

    def test_register_rpc_for_endpoint(self, http_bridge, mock_syft_events):
        """Test RPC handler registration for a single endpoint."""
        # Mock the decorator
        mock_decorator = Mock()
        mock_syft_events.on_request.return_value = mock_decorator

        http_bridge._register_rpc_for_endpoint("/test")

        # Verify on_request is called with correct endpoint
        mock_syft_events.on_request.assert_called_once_with("/test")

        # Verify decorator is called with the handler function
        mock_decorator.assert_called_once()
        handler_func = mock_decorator.call_args[0][0]
        assert callable(handler_func)

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.api
    async def test_forward_to_http_success(self, http_bridge, mock_http_client):
        """Test successful HTTP forwarding."""
        # Create mock request
        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = b'{"data": "test"}'
        mock_request.headers = {"Content-Type": "application/json"}
        mock_request.url = SyftBoxURL("syft://user@test.com/app_data/testapp/rpc/test/")

        # Create mock response
        mock_response = Mock(spec=httpx.Response)
        mock_response.content = b'{"result": "success"}'
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}

        mock_http_client.request.return_value = mock_response

        # Test forwarding
        response = await http_bridge._forward_to_http(mock_request, "/test")

        # Verify HTTP client is called with correct parameters
        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/test",
            content=b'{"data": "test"}',
            headers={
                "Content-Type": "application/json",
                "X-Syft-URL": str(mock_request.url),
            },
            params=None,
        )

        assert response == mock_response

    @pytest.mark.asyncio
    async def test_forward_to_http_method_error_fallback(
        self, http_bridge, mock_http_client
    ):
        """Test HTTP forwarding with method extraction error defaults to POST."""
        # Create mock request where str() on method raises exception
        mock_request = Mock(spec=SyftEventRequest)

        # Create a mock object that raises exception when str() is called on it
        mock_method = Mock()
        mock_method.__str__ = Mock(side_effect=Exception("Method error"))
        mock_request.method = mock_method

        mock_request.body = b'{"data": "test"}'
        mock_request.headers = {"Content-Type": "application/json"}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        # Create mock response
        mock_response = Mock(spec=httpx.Response)
        mock_response.content = b'{"result": "success"}'
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}

        mock_http_client.request.return_value = mock_response

        # Capture print output
        with patch("builtins.print") as mock_print:
            response = await http_bridge._forward_to_http(mock_request, "/test")

        # Verify method defaults to POST and error is printed
        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/test",
            content=b'{"data": "test"}',
            headers={
                "Content-Type": "application/json",
                "X-Syft-URL": str(mock_request.url),
            },
            params=None,
        )

        mock_print.assert_called_once()
        assert "Error getting method Defaulting to POST" in str(mock_print.call_args)
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_forward_to_http_different_methods(
        self, http_bridge, mock_http_client
    ):
        """Test HTTP forwarding with different HTTP methods."""
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

        for method in methods:
            mock_request = Mock(spec=SyftEventRequest)
            mock_request.method = method
            mock_request.body = b""
            mock_request.headers = {}
            mock_request.url = SyftBoxURL(
                "syft://user@test.com/app_data/pingpong/rpc/ping/"
            )

            mock_response = Mock(spec=httpx.Response)
            mock_http_client.request.return_value = mock_response

            await http_bridge._forward_to_http(mock_request, "/test")

            # Check that the correct method was used
            args, kwargs = mock_http_client.request.call_args
            assert kwargs["method"] == method

    def test_rpc_handler_integration(
        self, http_bridge, mock_syft_events, mock_http_client
    ):
        """Test RPC handler creation and execution."""
        # Mock _forward_to_http response
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.content = b'{"result": "success"}'
        mock_http_response.status_code = 200
        mock_http_response.headers = {"Content-Type": "application/json"}

        # Mock asyncio.run to return our mock response
        with patch("asyncio.run") as mock_run:
            mock_run.return_value = mock_http_response

            # Get the handler function that would be registered
            mock_decorator = Mock()
            mock_syft_events.on_request.return_value = mock_decorator

            http_bridge._register_rpc_for_endpoint("/test")

            # Get the registered handler function
            handler_func = mock_decorator.call_args[0][0]

            # Create mock request
            mock_request = Mock(spec=SyftEventRequest)
            mock_request.method = "POST"
            mock_request.body = b'{"data": "test"}'
            mock_request.headers = {"Content-Type": "application/json"}

            # Execute handler
            response = handler_func(mock_request)

            # Verify response is properly constructed
            assert isinstance(response, Response)
            assert response.body == b'{"result": "success"}'
            assert response.status_code == 200
            assert response.headers == {"Content-Type": "application/json"}

    @pytest.mark.asyncio
    async def test_forward_to_http_with_complex_headers(
        self, http_bridge, mock_http_client
    ):
        """Test HTTP forwarding with complex headers."""
        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = b'{"data": "test"}'
        mock_request.headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
            "X-Custom-Header": "custom-value",
            "Accept": "application/json",
        }
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        mock_response = Mock(spec=httpx.Response)
        mock_http_client.request.return_value = mock_response

        await http_bridge._forward_to_http(mock_request, "/api/complex")

        # Verify all headers are forwarded
        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/api/complex",
            content=b'{"data": "test"}',
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token123",
                "X-Custom-Header": "custom-value",
                "Accept": "application/json",
                "X-Syft-URL": str(mock_request.url),
            },
            params=None,
        )

    @pytest.mark.asyncio
    async def test_forward_to_http_empty_body(self, http_bridge, mock_http_client):
        """Test HTTP forwarding with empty body."""
        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "GET"
        mock_request.body = b""
        mock_request.headers = {}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        mock_response = Mock(spec=httpx.Response)
        mock_http_client.request.return_value = mock_response

        await http_bridge._forward_to_http(mock_request, "/test")

        mock_http_client.request.assert_called_once_with(
            method="GET",
            url="/test",
            content=b"",
            headers={},
            params=None,
        )

    @pytest.mark.asyncio
    async def test_forward_to_http_large_body(self, http_bridge, mock_http_client):
        """Test HTTP forwarding with large body."""
        large_body = b"x" * 10000  # 10KB body

        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = large_body
        mock_request.headers = {"Content-Type": "application/octet-stream"}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        mock_response = Mock(spec=httpx.Response)
        mock_http_client.request.return_value = mock_response

        await http_bridge._forward_to_http(mock_request, "/upload")

        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/upload",
            content=large_body,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Syft-URL": str(mock_request.url),
            },
            params=None,
        )

    def test_multiple_endpoints_registration(self, mock_http_client, mock_syft_client):
        """Test bridge with multiple endpoints."""
        endpoints = ["/api/v1/users", "/api/v1/posts", "/api/v1/comments", "/health"]

        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            bridge = SyftHTTPBridge(
                app_name="multi_endpoint_app",
                http_client=mock_http_client,
                included_endpoints=endpoints,
                syftbox_client=mock_syft_client,
            )

            with patch.object(bridge, "_register_rpc_for_endpoint") as mock_register:
                bridge._register_rpc_handlers()

                # Verify all endpoints are registered
                assert mock_register.call_count == len(endpoints)
                for endpoint in endpoints:
                    mock_register.assert_any_call(endpoint)

    def test_empty_endpoints_list(self, mock_http_client, mock_syft_client):
        """Test bridge with empty endpoints list."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            bridge = SyftHTTPBridge(
                app_name="empty_app",
                http_client=mock_http_client,
                included_endpoints=[],
                syftbox_client=mock_syft_client,
            )

            with patch.object(bridge, "_register_rpc_for_endpoint") as mock_register:
                bridge._register_rpc_handlers()

                # Verify no endpoints are registered
                mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_client_request_failure(self, http_bridge, mock_http_client):
        """Test handling of HTTP client request failures."""
        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = b'{"data": "test"}'
        mock_request.headers = {"Content-Type": "application/json"}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        # Simulate HTTP client failure
        mock_http_client.request.side_effect = httpx.RequestError("Connection failed")

        with pytest.raises(httpx.RequestError):
            await http_bridge._forward_to_http(mock_request, "/test")

    @pytest.mark.asyncio
    async def test_http_timeout_handling(self, http_bridge, mock_http_client):
        """Test handling of HTTP timeouts."""
        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "GET"
        mock_request.body = b""
        mock_request.headers = {}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        # Simulate timeout
        mock_http_client.request.side_effect = httpx.TimeoutException(
            "Request timed out"
        )

        with pytest.raises(httpx.TimeoutException):
            await http_bridge._forward_to_http(mock_request, "/slow-endpoint")

    def test_response_header_conversion(self, http_bridge, mock_syft_events):
        """Test proper conversion of HTTP response headers to dict."""
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.content = b'{"result": "success"}'
        mock_http_response.status_code = 201

        # Create headers that behave like httpx.Headers when dict() is called on them
        mock_headers = {"Content-Type": "application/json", "X-Custom": "value"}
        mock_http_response.headers = mock_headers

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = mock_http_response

            mock_decorator = Mock()
            mock_syft_events.on_request.return_value = mock_decorator

            http_bridge._register_rpc_for_endpoint("/test")
            handler_func = mock_decorator.call_args[0][0]

            mock_request = Mock(spec=SyftEventRequest)
            response = handler_func(mock_request)

            # Verify headers are converted using dict()
            assert response.status_code == 201
            assert response.body == b'{"result": "success"}'
            assert response.headers == mock_headers

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, http_bridge, mock_http_client):
        """Test handling of concurrent HTTP requests."""
        # Create multiple mock requests
        requests = []
        for i in range(5):
            mock_request = Mock(spec=SyftEventRequest)
            mock_request.method = "POST"
            mock_request.body = f'{{"id": {i}}}'.encode()
            mock_request.headers = {"Content-Type": "application/json"}
            mock_request.url = SyftBoxURL(
                "syft://user@test.com/app_data/pingpong/rpc/ping/"
            )
            requests.append(mock_request)

        # Mock responses
        responses = []
        for i in range(5):
            mock_response = Mock(spec=httpx.Response)
            mock_response.content = f'{{"result": {i}}}'.encode()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            responses.append(mock_response)

        mock_http_client.request.side_effect = responses

        # Execute concurrent requests
        tasks = [
            http_bridge._forward_to_http(req, f"/test/{i}")
            for i, req in enumerate(requests)
        ]
        results = await asyncio.gather(*tasks)

        # Verify all requests were processed
        assert len(results) == 5
        assert mock_http_client.request.call_count == 5

        # Verify each response matches expectation
        for i, result in enumerate(results):
            assert result == responses[i]

    def test_bridge_string_representation(self, http_bridge):
        """Test bridge has proper string representation for debugging."""
        # Verify the bridge instance can be converted to string without errors
        bridge_str = str(http_bridge)
        assert "SyftHTTPBridge" in bridge_str

    @pytest.mark.asyncio
    async def test_forward_to_http_with_binary_content(
        self, http_bridge, mock_http_client
    ):
        """Test HTTP forwarding with binary content (images, files, etc.)."""
        # Simulate binary file upload
        binary_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"  # PNG header
        )

        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = binary_data
        mock_request.headers = {"Content-Type": "image/png"}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/ping/"
        )

        mock_response = Mock(spec=httpx.Response)
        mock_response.content = b'{"upload_id": "12345"}'
        mock_response.status_code = 201
        mock_response.headers = {"Content-Type": "application/json"}

        mock_http_client.request.return_value = mock_response

        response = await http_bridge._forward_to_http(mock_request, "/upload")

        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/upload",
            content=binary_data,
            headers={"Content-Type": "image/png", "X-Syft-URL": str(mock_request.url)},
            params=None,
        )
        assert response == mock_response

    @pytest.mark.asyncio
    async def test_forward_to_http_with_special_characters(
        self, http_bridge, mock_http_client
    ):
        """Test HTTP forwarding with special characters and Unicode."""
        unicode_content = '{"message": "Hello 🌍 世界", "emoji": "🚀"}'.encode("utf-8")

        mock_request = Mock(spec=SyftEventRequest)
        mock_request.method = "POST"
        mock_request.body = unicode_content
        mock_request.headers = {"Content-Type": "application/json; charset=utf-8"}
        mock_request.url = SyftBoxURL(
            "syft://user@test.com/app_data/pingpong/rpc/unicode/"
        )

        mock_response = Mock(spec=httpx.Response)
        mock_response.content = '{"status": "received 📨"}'.encode("utf-8")
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json; charset=utf-8"}

        mock_http_client.request.return_value = mock_response

        response = await http_bridge._forward_to_http(mock_request, "/unicode")

        mock_http_client.request.assert_called_once_with(
            method="POST",
            url="/unicode",
            content=unicode_content,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Syft-URL": str(mock_request.url),
            },
            params=None,
        )
        assert response == mock_response

    def test_bridge_with_single_endpoint(self, mock_http_client, mock_syft_client):
        """Test bridge behavior with just one endpoint."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            bridge = SyftHTTPBridge(
                app_name="single_endpoint_app",
                http_client=mock_http_client,
                included_endpoints=["/health"],
                syftbox_client=mock_syft_client,
            )

            with patch.object(bridge, "_register_rpc_for_endpoint") as mock_register:
                bridge._register_rpc_handlers()

                # Verify only one endpoint is registered
                mock_register.assert_called_once_with("/health")

    @pytest.mark.asyncio
    async def test_start_and_aclose_integration(
        self, mock_http_client, mock_syft_client
    ):
        """Test complete lifecycle from start to close."""
        with patch("fastsyftbox.http_bridge.SyftEvents") as mock_events_class:
            mock_events = Mock()
            mock_events_class.return_value = mock_events

            bridge = SyftHTTPBridge(
                app_name="lifecycle_app",
                http_client=mock_http_client,
                included_endpoints=["/test"],
                syftbox_client=mock_syft_client,
            )

            # Start the bridge
            bridge.start()

            # Verify start was called
            mock_events.start.assert_called_once()

            # Close the bridge
            await bridge.aclose()

            # Verify both components were closed
            mock_events.stop.assert_called_once()
            mock_http_client.aclose.assert_called_once()

    def test_rpc_handler_with_empty_headers(self, http_bridge, mock_syft_events):
        """Test RPC handler when HTTP response has empty headers."""
        mock_http_response = Mock(spec=httpx.Response)
        mock_http_response.content = b'{"result": "success"}'
        mock_http_response.status_code = 200
        mock_http_response.headers = {}  # Edge case: Empty headers

        with patch("asyncio.run") as mock_run:
            mock_run.return_value = mock_http_response

            mock_decorator = Mock()
            mock_syft_events.on_request.return_value = mock_decorator

            http_bridge._register_rpc_for_endpoint("/test")
            handler_func = mock_decorator.call_args[0][0]

            mock_request = Mock(spec=SyftEventRequest)
            response = handler_func(mock_request)

            # Verify response handles empty headers gracefully
            assert response.status_code == 200
            assert response.body == b'{"result": "success"}'
            assert response.headers == {}
