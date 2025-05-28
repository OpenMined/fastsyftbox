from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncContextManager, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute, BaseRoute
from pydantic import BaseModel
from syft_core import Client
from syft_event.server2 import SyftEvents
from syft_event.types import Request as SyftEventRequest
from syft_event.types import Response

SYFT_DOCS_TAG = "syft_docs"


class SyftHTTPBridge:
    def __init__(
        self,
        app_name: str,
        http_client: httpx.AsyncClient,
        included_endpoints: list[str],
        syftbox_client: Optional[Client] = None,
    ):
        self.app = app
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
        return await self.app_client.request(
            method=str(request.method),
            url=path,
            content=request.body,
            headers=request.headers,
        )


class SyftboxFastAPI(FastAPI):
    def __init__(
        self,
        app_name: str,
        syftbox_client: Optional[Client] = None,
        lifespan: Optional[AsyncContextManager] = None,
        syftbox_endpoint_tags: Optional[list[str]] = None,
        include_syft_openapi: bool = True,
        **kwargs,
    ):
        self.app_name = app_name
        self.syftbox_client = syftbox_client
        self.user_lifespan = lifespan
        self.bridge: Optional[SyftHTTPBridge] = None
        self.syftbox_endpoint_tags = syftbox_endpoint_tags
        self.include_syft_openapi = include_syft_openapi

        # Wrap user lifespan with bridge lifespan
        super().__init__(title=app_name, lifespan=self._combined_lifespan, **kwargs)

    @asynccontextmanager
    async def _combined_lifespan(self, app: FastAPI):
        # Discover Syft-enabled routes and generate OpenAPI
        syft_routes = list(self._discover_syft_routes())
        syft_endpoints = [route.path for route in syft_routes]
        self._create_syft_openapi_endpoints(syft_routes)
        syft_docs_routes = self._get_api_routes_with_tags([SYFT_DOCS_TAG])
        syft_docs_endpoints = [route.path for route in syft_docs_routes]

        # app_client transports requests directly to the FastAPI app
        app_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        )

        # Bridge forwards syft requests to the FastAPI app
        self.bridge = SyftHTTPBridge(
            app_name=self.app_name,
            http_client=app_client,
            included_endpoints=syft_endpoints + syft_docs_endpoints,
            syftbox_client=self.syftbox_client,
        )
        self.bridge.start()

        # Run user lifespan if provided
        if self.user_lifespan:
            async with self.user_lifespan(app):
                yield
        else:
            yield

        # Stop bridge
        if self.bridge:
            await self.bridge.aclose()

    def _discover_syft_routes(self) -> list[APIRoute]:
        if self.syftbox_endpoint_tags:
            return self._get_api_routes_with_tags(self.syftbox_endpoint_tags)
        else:
            return [route for route in self.routes if isinstance(route, APIRoute)]

    def _get_api_routes_with_tags(self, tags: list[str]) -> list[APIRoute]:
        return [
            route
            for route in self.routes
            if isinstance(route, APIRoute) and any(tag in route.tags for tag in tags)
        ]

    def _create_syft_openapi_endpoints(self, syft_routes: list[BaseRoute]) -> None:
        """Generate OpenAPI schema for Syft-enabled endpoints only"""

        if not self.include_syft_openapi:
            return
        # Create filtered OpenAPI schema
        openapi_schema = get_openapi(
            title=f"{self.title} - Syft RPC",
            version=self.version,
            description="Auto-generated schema for Syft-rpc endpoints",
            routes=syft_routes,
        )

        @self.get("/syft/openapi.json", include_in_schema=False, tags=["syft_docs"])
        def get_syft_openapi() -> JSONResponse:
            return JSONResponse(content=openapi_schema)

        # TODO swagger page over syftbox?


########################################################################################


# Example usage
@asynccontextmanager
async def my_lifespan(app: FastAPI):
    print("User startup")
    yield
    print("User shutdown")


app = SyftboxFastAPI(
    app_name="my_app",
    lifespan=my_lifespan,
    syftbox_endpoint_tags=["syft_endpoint"],  # Only include endpoints with this tag
    include_syft_openapi=True,  # Create OpenAPI endpoints for syft-rpc routes
)


class Ping(BaseModel):
    message: str


class Pong(BaseModel):
    response: str


@app.post("/ping", tags=["syft_endpoint"])
def ping_endpoint(ping: Ping) -> Pong:
    return Pong(response=f"Hello, {ping.message}!")


@app.get("/health", tags=["syft_endpoint"])
def health_endpoint():
    """
    Health check endpoint to verify the service is running.

    Returns:
        dict: A simple JSON response indicating the service status.
    """
    return {"status": "ok"}


@app.get("/")
def home(request: Request) -> HTMLResponse:
    # Not exposed over syft-rpc, since the tag 'syft_endpoint' is not used
    app_name = request.app.title
    return HTMLResponse(
        content=f"<html><body><h1>Welcome to {app_name}!</h1></body></html>",
        status_code=200,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=8000)
