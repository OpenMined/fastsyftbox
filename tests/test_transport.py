"""Tests for transport classes including SyftFileSystemTransport and SimpleRPCClient."""

import json
from pathlib import Path
from unittest.mock import Mock, PropertyMock, call, patch

import httpx
import pytest
from syft_core import Client
from syft_event.server2 import SyftEvents
from syft_event.types import Request, Response
from syft_core import SyftBoxURL
from syft_rpc import rpc

from fastsyftbox.simple_client import SimpleRPCClient
from fastsyftbox.direct_http_transport import DirectSyftboxTransport
from fastsyftbox.transport import SyftFileSystemTransport, _read_content


class TestReadContent:
    """Test cases for the _read_content helper function."""

    def test_read_content_request_with_content(self):
        """Test reading content from a Request that already has content."""
        mock_request = Mock(spec=Request)
        mock_request.content = b"test content"
        
        result = _read_content(mock_request)
        assert result == b"test content"

    def test_read_content_request_needs_read(self):
        """Test reading content from a Request that needs to be read."""
        mock_request = Mock()
        mock_request.read = Mock(return_value=b"read content")
        
        # Mock the content property to raise httpx.RequestNotRead on first access
        type(mock_request).content = PropertyMock(
            side_effect=[httpx.RequestNotRead(), b"read content"]
        )
        
        result = _read_content(mock_request)
        assert result == b"read content"
        mock_request.read.assert_called_once()

    def test_read_content_response_with_content(self):
        """Test reading content from a Response that already has content."""
        mock_response = Mock(spec=Response)
        mock_response.content = b"response content"
        
        result = _read_content(mock_response)
        assert result == b"response content"

    def test_read_content_response_needs_read(self):
        """Test reading content from a Response that needs to be read."""
        mock_response = Mock()
        mock_response.read = Mock(return_value=b"read response")
        
        # Mock the content property to raise httpx.ResponseNotRead on first access
        type(mock_response).content = PropertyMock(
            side_effect=[httpx.ResponseNotRead(), b"read response"]
        )
        
        result = _read_content(mock_response)
        assert result == b"read response"
        mock_response.read.assert_called_once()

    def test_read_content_invalid_type(self):
        """Test reading content from an invalid type."""
        with pytest.raises(AttributeError):
            _read_content("invalid")


class TestSyftFileSystemTransport:
    """Test cases for SyftFileSystemTransport class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SyftBox client."""
        mock = Mock(spec=Client)
        mock.api_data.return_value = Path("/path/to/api_data")
        return mock

    @pytest.fixture
    def mock_rpc(self):
        """Create a mock RPC object."""
        with patch("fastsyftbox.transport.rpc") as mock:
            yield mock

    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        app_owner = "owner@example.com"
        app_name = "testapp"
        data_dir = Path("/custom/data")
        sender_email = "sender@example.com"
        
        transport = SyftFileSystemTransport(
            app_owner=app_owner,
            app_name=app_name,
            data_dir=data_dir,
            sender_email=sender_email
        )
        
        assert transport.app_owner == app_owner
        assert transport.app_name == app_name
        assert transport.data_dir == data_dir
        assert transport.sender_email == sender_email
        assert transport.app_dir == data_dir / app_owner / "app_data" / app_name
        assert transport.rpc_dir == transport.app_dir / "rpc"

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        transport = SyftFileSystemTransport(
            app_owner="owner@example.com",
            app_name="testapp",
            data_dir=Path("/tmp/data")
        )
        
        assert transport.app_owner == "owner@example.com"
        assert transport.app_name == "testapp"
        assert transport.data_dir == Path("/tmp/data")
        assert transport.sender_email == "guest@syftbox.com"  # Default value

    @patch("fastsyftbox.transport.SyftBoxClient")
    def test_handle_request_success(self, mock_client_class, mock_rpc):
        """Test successful request handling."""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        transport = SyftFileSystemTransport(
            app_owner="owner@example.com",
            app_name="testapp",
            data_dir=Path("/tmp/data"),
            sender_email="sender@example.com"
        )
        
        request = httpx.Request("POST", "http://example.com/test")
        request_content = b'{"test": "data"}'
        request._content = request_content
        
        # Mock RPC response with proper status code
        from syft_rpc.protocol import SyftStatus
        mock_response = Mock()
        mock_response.status_code = SyftStatus.SYFT_200_OK
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.body = b'{"result": "success"}'
        
        # Mock the future object
        mock_future = Mock()
        mock_future.wait.return_value = mock_response
        mock_rpc.send.return_value = mock_future
        mock_rpc.parse_duration.return_value = Mock(seconds=5)
        
        # Execute
        response = transport.handle_request(request)
        
        # Assert
        assert isinstance(response, httpx.Response)
        assert response.status_code == 200
        assert response.content == b'{"result": "success"}'
        assert response.headers["Content-Type"] == "application/json"
        
        # Verify RPC call
        mock_rpc.send.assert_called_once()
        call_kwargs = mock_rpc.send.call_args[1]
        
        # Check the RPC request parameters
        assert str(call_kwargs['url']).startswith("syft://owner@example.com/app_data/testapp/rpc/")
        assert call_kwargs['method'] == "POST"
        assert call_kwargs['body'] == request_content
        assert call_kwargs['client'] == mock_client
        assert call_kwargs['cache'] is False

    @patch("fastsyftbox.transport.SyftBoxClient")
    def test_handle_request_with_custom_headers(self, mock_client_class, mock_rpc):
        """Test request handling with custom headers."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        transport = SyftFileSystemTransport(
            app_owner="owner@example.com",
            app_name="testapp",
            data_dir=Path("/tmp/data"),
            sender_email="custom@sender.com"
        )
        
        # Create request with custom headers
        headers = {"X-Custom": "value", "Authorization": "Bearer token"}
        request = httpx.Request("GET", "http://example.com/api", headers=headers)
        request._content = b""
        
        # Mock RPC response
        from syft_rpc.protocol import SyftStatus
        mock_response = Mock()
        mock_response.status_code = SyftStatus.SYFT_200_OK
        mock_response.headers = {}
        mock_response.body = b"OK"
        
        mock_future = Mock()
        mock_future.wait.return_value = mock_response
        mock_rpc.send.return_value = mock_future
        mock_rpc.parse_duration.return_value = Mock(seconds=5)
        
        # Execute
        response = transport.handle_request(request)
        
        # Verify headers were passed through
        mock_rpc.send.assert_called_once()
        call_kwargs = mock_rpc.send.call_args[1]
        sent_headers = call_kwargs['headers']
        # httpx headers need to be extracted using items()
        assert "x-custom" in sent_headers or "X-Custom" in sent_headers
        assert "authorization" in sent_headers or "Authorization" in sent_headers

    def test_close_method(self):
        """Test close method (should be no-op)."""
        transport = SyftFileSystemTransport(
            app_owner="owner@example.com",
            app_name="testapp",
            data_dir=Path("/tmp/data")
        )
        
        # Should not raise any errors
        transport.close()

    def test_from_config_placeholder(self):
        """Test from_config classmethod (currently a placeholder)."""
        # The method exists but doesn't do anything (just passes)
        result = SyftFileSystemTransport.from_config(Path("/config/path"))
        assert result is None  # The method returns None


class TestSimpleRPCClient:
    """Test cases for SimpleRPCClient class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock SyftBox client."""
        mock = Mock(spec=Client)
        mock.api_data.return_value = Path("/path/to/api_data")
        return mock

    def test_init_local_transport_with_data_dir(self):
        """Test initialization with local transport using data_dir."""
        client = SimpleRPCClient(
            data_dir="/custom/data",
            app_name="testapp",
            use_local_transport=True
        )
        
        # Verify transport is SyftFileSystemTransport
        assert hasattr(client, "_transport")
        transport = client._transport
        assert isinstance(transport, SyftFileSystemTransport)
        assert transport.app_owner == "guest@syftbox.com"
        assert transport.sender_email == "guest@syft.org"

    def test_init_local_transport_with_app_name_only(self):
        """Test initialization with local transport using app_name only."""
        client = SimpleRPCClient(
            app_name="testapp",
            use_local_transport=True
        )
        
        # Verify default data_dir is used
        assert hasattr(client, "_transport")
        transport = client._transport
        assert isinstance(transport, SyftFileSystemTransport)
        assert transport.data_dir == Path("/tmp/testapp")
        assert transport.app_owner == "guest@syftbox.com"

    def test_init_local_transport_missing_params(self):
        """Test initialization fails when missing required params for local transport."""
        with pytest.raises(ValueError, match="data_dir or app_name must be provided"):
            SimpleRPCClient(use_local_transport=True)

    @patch("fastsyftbox.simple_client.DirectSyftboxTransport")
    def test_init_remote_transport(self, mock_transport_class):
        """Test initialization with remote transport."""
        mock_transport = Mock()
        mock_transport_class.return_value = mock_transport
        
        client = SimpleRPCClient(
            app_owner="owner@example.com",
            app_name="testapp",
            sender_email="sender@example.com",
            use_local_transport=False
        )
        
        # Verify DirectSyftboxTransport was created
        mock_transport_class.assert_called_once_with(
            app_owner="owner@example.com",
            app_name="testapp",
            sender_email="sender@example.com"
        )
        assert client._transport == mock_transport

    def test_init_remote_transport_missing_params(self):
        """Test initialization fails when missing required params for remote transport."""
        with pytest.raises(ValueError, match="app_owner and app_name must be provided"):
            SimpleRPCClient(use_local_transport=False, app_name="test")
        
        with pytest.raises(ValueError, match="app_owner and app_name must be provided"):
            SimpleRPCClient(use_local_transport=False, app_owner="owner@example.com")

    def test_for_local_transport_classmethod(self):
        """Test for_local_transport class method."""
        client = SimpleRPCClient.for_local_transport(
            app_name="testapp",
            data_dir="/custom/path"
        )
        
        assert isinstance(client, SimpleRPCClient)
        assert hasattr(client, "_transport")
        assert isinstance(client._transport, SyftFileSystemTransport)

    @patch("fastsyftbox.simple_client.DirectSyftboxTransport")
    def test_for_syftbox_transport_classmethod(self, mock_transport_class):
        """Test for_syftbox_transport class method."""
        mock_transport = Mock()
        mock_transport_class.return_value = mock_transport
        
        client = SimpleRPCClient.for_syftbox_transport(
            app_owner="owner@example.com",
            app_name="testapp",
            sender_email="custom@sender.com"
        )
        
        assert isinstance(client, SimpleRPCClient)
        mock_transport_class.assert_called_once_with(
            app_owner="owner@example.com",
            app_name="testapp",
            sender_email="custom@sender.com"
        )

    def test_inherits_from_httpx_client(self):
        """Test that SimpleRPCClient inherits from httpx.Client."""
        assert issubclass(SimpleRPCClient, httpx.Client)

    @patch("fastsyftbox.simple_client.DirectSyftboxTransport")
    def test_extra_kwargs_passed_to_parent(self, mock_transport_class):
        """Test that extra kwargs are passed to parent httpx.Client."""
        mock_transport = Mock()
        mock_transport_class.return_value = mock_transport
        
        # Create client with extra httpx.Client parameters
        client = SimpleRPCClient(
            app_owner="owner@example.com",
            app_name="testapp",
            use_local_transport=False,
            timeout=30.0,
            verify=False,
            follow_redirects=True
        )
        
        # These attributes should be set on the httpx.Client
        # Check that timeout was passed through
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.connect == 30.0
        
        # Check that follow_redirects was passed through
        assert client.follow_redirects is True
        
        # verify is not exposed as an attribute but is used internally