from __future__ import annotations

import logging
from typing import Optional

import httpx
import uvicorn.logging
from syft_core import Client
from syft_event.server2 import SyftEvents
from syft_event.types import Request as SyftEventRequest
from syft_event.types import Response

handler = logging.StreamHandler()
formatter = uvicorn.logging.DefaultFormatter(fmt="%(levelprefix)s %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger("syftbox.http_bridge")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(handler)


from fastsyftbox.constants import SYFT_FROM_HEADER, SYFT_URL_HEADER

MAX_HTTP_TIMEOUT_SECONDS = 30


class SyftHTTPBridge:
    def __init__(
        self,
        app_name: str,
        http_client: httpx.AsyncClient,
        included_endpoints: list[str],
        syftbox_client: Optional[Client] = None,
    ):
        self.syft_events = SyftEvents(app_name, client=syftbox_client)
        self.included_endpoints = included_endpoints
        self.app_client = http_client  # Add the missing app_client attribute

    def start(self) -> None:
        self._register_rpc_handlers()
        self.syft_events.start()

    async def aclose(self) -> None:
        self.syft_events.stop()
        await self.app_client.aclose()

    def __enter__(self) -> SyftHTTPBridge:
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def _forward_to_http(
        self, request: SyftEventRequest, path: str
    ) -> httpx.Response:
        """Forward RPC request to HTTP endpoint."""
        method = self._get_method(request)
        headers = self._prepare_headers(request)
        response = await self.app_client.request(
            method=method,
            url=path,
            content=request.body,
            headers=headers,
            params=request.url.query or None,
        )
        return response

    def _get_method(self, request: SyftEventRequest) -> str:
        """Extract HTTP method from request."""
        try:
            return str(request.method) if request.method else "POST"
        except Exception as e:
            print(f"Error getting method Defaulting to POST: {e}")
            return "POST"

    def _prepare_headers(self, request: SyftEventRequest) -> dict:
        """Prepare headers for HTTP request."""
        headers = request.headers or {}
        headers[SYFT_URL_HEADER] = str(request.url)
        sender = getattr(request, "sender", None)
        if sender:
            headers[SYFT_FROM_HEADER] = str(sender)
        return headers

    def _register_rpc_handlers(self) -> None:
        for endpoint in self.included_endpoints:
            self._register_rpc_for_endpoint(endpoint)

    def _register_rpc_for_endpoint(self, endpoint: str) -> None:
        @self.syft_events.on_request(endpoint)
        async def rpc_handler(request: SyftEventRequest) -> Response:
            http_response = await self._forward_to_http(request, endpoint)
            return Response(
                body=http_response.content,
                status_code=http_response.status_code,
                headers=dict(http_response.headers),
            )
