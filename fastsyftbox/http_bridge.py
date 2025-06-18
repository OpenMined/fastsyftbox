from __future__ import annotations

import asyncio
import threading
from typing import Optional

import httpx
from syft_core import Client
from syft_event.server2 import SyftEvents
from syft_event.types import Request as SyftEventRequest
from syft_event.types import Response

MAX_HTTP_TIMEOUT_SECONDS = 30


class EventLoopManager:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        def run_event_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def check_stop():
                while not self._stop_event.is_set():
                    await asyncio.sleep(0.1)

            self._loop.run_until_complete(check_stop())

        self._thread = threading.Thread(target=run_event_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._loop


class HTTPForwarder:
    def __init__(self, client: httpx.AsyncClient, event_loop: EventLoopManager, bridge):
        self.client = client
        self.event_loop = event_loop
        self.bridge = bridge

    def forward(self, request: SyftEventRequest, path: str) -> httpx.Response:
        if not self.event_loop.loop:
            raise RuntimeError("Event loop not initialized")

        method = self.bridge._get_method(request)
        headers = self.bridge._prepare_headers(request)

        coro = self.client.request(
            method=method,
            url=path,
            content=request.body,
            headers=headers,
            params=request.url.query or None,
        )

        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop.loop)
        return future.result(timeout=MAX_HTTP_TIMEOUT_SECONDS)


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
        self.event_loop = EventLoopManager()
        self.http_forwarder = HTTPForwarder(http_client, self.event_loop, self)

    def start(self) -> None:
        self.event_loop.start()
        self._register_rpc_handlers()
        self.syft_events.start()

    async def aclose(self) -> None:
        self.syft_events.stop()
        self.event_loop.stop()
        await self.http_forwarder.client.aclose()

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
        headers["X-Syft-URL"] = str(request.url)
        return headers

    def _register_rpc_handlers(self) -> None:
        for endpoint in self.included_endpoints:
            self._register_rpc_for_endpoint(endpoint)

    def _register_rpc_for_endpoint(self, endpoint: str) -> None:
        @self.syft_events.on_request(endpoint)
        def rpc_handler(request: SyftEventRequest) -> Response:
            http_response = asyncio.run(self._forward_to_http(request, endpoint))
            return Response(
                body=http_response.content,
                status_code=http_response.status_code,
                headers=dict(http_response.headers),
            )
