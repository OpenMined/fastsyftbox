import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig
from syft_event import SyftEvents


class Syftbox:
    def __init__(
        self,
        app: FastAPI,
        name: str,
        config: SyftClientConfig = None,
    ):
        self.name = name
        self.app = app

        # Load config + client
        self.config = config if config is not None else SyftClientConfig.load()
        self.client = SyftboxClient(self.config)

        # setup app data directory
        self.current_dir = Path(__file__).parent
        self.app_data_dir = (
            Path(self.client.config.data_dir) / "private" / "app_data" / name
        )
        self.app_data_dir.mkdir(parents=True, exist_ok=True)

        # Setup event system
        self.box = SyftEvents(app_name=name)
        self.client.makedirs(self.client.datasite_path / "public" / name)
        self.debug = False
        self.debug_publish = False
        # Attach lifespan
        self._attach_lifespan()

    def _attach_lifespan(self):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, self.box.run_forever)
            yield

        self.app.router.lifespan_context = lifespan

    def on_request(self, path: str):
        """Decorator to register an on_request handler with the SyftEvents box."""
        return self.box.on_request(path)

    def publish_file_path(self, local_path: Path, in_datasite_path: Path):
        publish_path = self.client.datasite_path / in_datasite_path
        publish_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(local_path, publish_path)

    def publish_contents(self, file_contents: str, in_datasite_path: Path):
        publish_path = self.client.datasite_path / in_datasite_path
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
            str(self.config.server_url) or "https://syftboxdev.openmined.org/",
        )
        content = content.replace("{{ from_email }}", "guest@syft.local")
        content = content.replace("{{ to_email }}", self.client.email)
        content = content.replace("{{ app_name }}", self.name)
        content = content.replace("{{ app_endpoint }}", endpoint)
        content = content.replace("{{ request_body }}", str(example_request))

        default_headers = [
            {"key": "x-syft-msg-type", "value": "request"},
            {"key": "x-syft-from", "value": "guest@syft.local"},
            {"key": "x-syft-to", "value": self.client.email},
            {"key": "x-syft-app", "value": self.name},
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

        @self.app.get("/rpc-debug", response_class=HTMLResponse)
        def get_rpc_debug():
            # warning: hot-reload depends on app.py reload
            return self.make_rpc_debug_page(endpoint, example_request)

        rendered_content = self.make_rpc_debug_page(endpoint, example_request)

        if publish:
            # Define the path in the datasite where the file should be published
            in_datasite_path = Path("public") / self.name / "rpc-debug.html"
            self.publish_contents(rendered_content, in_datasite_path)
            datasite_url = f"{self.config.server_url}datasites/{self.client.email}"
            url = f"{datasite_url}/public/{self.name}/rpc-debug.html"
            print(f"🚀 Successfully Published rpc-debug to:\n🌐 URL: {url}")

    def get_debug_urls(self):
        """
        Returns the URLs of the RPC debug tool
        """

        html = ""
        if self.debug:
            html = "<a href='/rpc-debug'>Local RPC Debug</a>"
            if self.debug_publish:
                datasite_url = f"{self.config.server_url}datasites/{self.client.email}"
                url = f"{datasite_url}/public/{self.name}/rpc-debug.html"
                html += f"<br /><a href='{url}'>Published RPC Debug</a>"
        return html
