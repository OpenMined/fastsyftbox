from __future__ import annotations

import asyncio
from typing import Optional

import httpx
from syft_core import Client
from syft_event.server2 import SyftEvents
from syft_event.types import Request as SyftEventRequest
from syft_event.types import Response


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
        self.app_client = http_client

    def start(self) -> None:
        self.syft_events.start()
        self._register_rpc_handlers()

    async def aclose(self) -> None:
        self.syft_events.stop()
        await self.app_client.aclose()

    def _register_rpc_handlers(self) -> None:
        for endpoint in self.included_endpoints:
            self._register_rpc_for_endpoint(endpoint)

    def _register_rpc_for_endpoint(self, endpoint: str) -> None:
        @self.syft_events.on_request(endpoint)
        def rpc_handler(request: SyftEventRequest) -> Response:
            # TODO async support for syft-events
            http_response = asyncio.run(self._forward_to_http(request, endpoint))
            return Response(
                body=http_response.content,
                status_code=http_response.status_code,
                headers=dict(http_response.headers),
            )

    async def _forward_to_http(
        self, request: SyftEventRequest, path: str
    ) -> httpx.Response:
        method = "POST"
        try:
            method = str(request.method)
        except Exception as e:
            # TODO remove once the events library is fixed
            print("Error getting method Defaulting to POST", e)
            pass

        return await self.app_client.request(
            method=method,
            url=path,
            content=request.body,
            headers=request.headers,
        )
