from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncContextManager, Optional

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute, BaseRoute
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig

from .http_bridge import SyftHTTPBridge

SYFT_DOCS_TAG = "syft_docs"


class FastSyftBox(FastAPI):
    def __init__(
        self,
        app_name: str,
        syftbox_config: Optional[SyftClientConfig] = None,
        lifespan: Optional[AsyncContextManager] = None,
        syftbox_endpoint_tags: Optional[list[str]] = None,
        include_syft_openapi: bool = True,
        **kwargs,
    ):
        self.app_name = app_name
        self.syftbox_config = (
            syftbox_config if syftbox_config is not None else SyftClientConfig.load()
        )
        self.syftbox_client = SyftboxClient(self.syftbox_config)
        self.user_lifespan = lifespan
        self.bridge: Optional[SyftHTTPBridge] = None
        self.syftbox_endpoint_tags = syftbox_endpoint_tags
        self.include_syft_openapi = include_syft_openapi
        self.current_dir = Path(__file__).parent

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
            async with self.user_lifespan(self):
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

    def publish_file_path(self, local_path: Path, in_datasite_path: Path):
        publish_path = self.syftbox_client.datasite_path / in_datasite_path
        publish_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(local_path, publish_path)

    def publish_contents(self, file_contents: str, in_datasite_path: Path):
        publish_path = self.syftbox_client.datasite_path / in_datasite_path
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        with open(publish_path, "w") as file:
            file.write(file_contents)

    def make_rpc_debug_page(self, endpoint: str, example_request: str):
        debug_page = self.current_dir / "app_template" / "assets" / "rpc-debug.html"
        with open(debug_page, "r") as file:
            debug_page_content = file.read()

        css_path = (
            self.current_dir / "app_template" / "assets" / "css" / "rpc-debug.css"
        )
        with open(css_path, "r") as file:
            css_content = file.read()
        css_tag = f"<style>{css_content}</style>"

        js_sdk_path = (
            self.current_dir / "app_template" / "assets" / "js" / "syftbox-sdk.js"
        )
        with open(js_sdk_path, "r") as file:
            js_sdk_content = file.read()

        js_sdk_tag = f"<script>{js_sdk_content}</script>"

        js_rpc_debug_path = (
            self.current_dir / "app_template" / "assets" / "js" / "rpc-debug.js"
        )
        with open(js_rpc_debug_path, "r") as file:
            js_rpc_debug_content = file.read()
        js_rpc_debug_tag = f"<script>{js_rpc_debug_content}</script>"

        content = debug_page_content
        content = content.replace("{{ css }}", css_tag)
        content = content.replace("{{ js_sdk }}", js_sdk_tag)
        content = content.replace("{{ js_rpc_debug }}", js_rpc_debug_tag)
        content = content.replace(
            "{{ server_url }}",
            str(self.syftbox_config.server_url) or "https://syftboxdev.openmined.org/",
        )
        content = content.replace("{{ from_email }}", "guest@syft.local")
        content = content.replace("{{ to_email }}", self.syftbox_client.email)
        content = content.replace("{{ app_name }}", self.app_name)
        content = content.replace("{{ app_endpoint }}", endpoint)
        content = content.replace("{{ request_body }}", str(example_request))

        default_headers = [
            {"key": "x-syft-msg-type", "value": "request"},
            {"key": "x-syft-from", "value": "guest@syft.local"},
            {"key": "x-syft-to", "value": self.syftbox_client.email},
            {"key": "x-syft-app", "value": self.app_name},
            {"key": "x-syft-appep", "value": endpoint},
            {"key": "x-syft-method", "value": "POST"},
            {"key": "x-syft-timeout", "value": "5000"},
            {"key": "Content-Type", "value": "application/json"},
        ]

        headers_content = "[{}]".format(
            ", ".join(
                f"{{ key: '{header['key']}', value: '{header['value']}' }}"
                for header in default_headers
            )
        )
        content = content.replace("{{ headers }}", headers_content)

        headers_content = "[{}]".format(
            ", ".join(
                f"{{ key: '{header['key']}', value: '{header['value']}' }}"
                for header in [{"key": "Content-Type", "value": "application/json"}]
            )
        )
        content = content.replace("{{ headers }}", headers_content)

        return content

    def enable_debug_tool(
        self, endpoint: str, example_request: str, publish: bool = False
    ):
        """
        Publishes the dynamically generated RPC debug tool HTML page to the datasite.
        """
        self.debug = True
        self.debug_publish = publish

        @self.get("/rpc-debug", response_class=HTMLResponse)
        def get_rpc_debug():
            # warning: hot-reload depends on app.py reload
            return self.make_rpc_debug_page(endpoint, example_request)

        rendered_content = self.make_rpc_debug_page(endpoint, example_request)

        if publish:
            # Define the path in the datasite where the file should be published
            in_datasite_path = Path("public") / self.app_name / "rpc-debug.html"
            self.publish_contents(rendered_content, in_datasite_path)
            datasite_url = (
                f"{self.syftbox_config.server_url}datasites/{self.syftbox_client.email}"
            )
            url = f"{datasite_url}/public/{self.app_name}/rpc-debug.html"
            print(f"🚀 Successfully Published rpc-debug to:\n🌐 URL: {url}")

    def get_debug_urls(self):
        """
        Returns the URLs of the RPC debug tool
        """

        html = ""
        if self.debug:
            html = "<a href='/rpc-debug'>Local RPC Debug</a>"
            if self.debug_publish:
                datasite_url = f"{self.syftbox_config.server_url}datasites/{self.syftbox_client.email}"
                url = f"{datasite_url}/public/{self.app_name}/rpc-debug.html"
                html += f"<br /><a href='{url}'>Published RPC Debug</a>"
        return html
