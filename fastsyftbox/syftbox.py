import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import jinja2
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

        template = jinja2.Template(debug_page_content)
        content = {
            "server_url": str(self.config.server_url)
            or "https://syftboxdev.openmined.org/",
            "from_email": "guest@syft.local",
            "to_email": self.client.email,
            "app_name": self.name,
            "app_endpoint": endpoint,
            "headers": [{"key": "Content-Type", "value": "application/json"}],
            "request_body": str(example_request),
        }

        try:
            rendered_content = template.render(**content)
        except jinja2.exceptions.UndefinedError as e:
            print(f"Template rendering error: {e}")
            return "Error rendering template"

        return rendered_content

    def enable_debug_tool(
        self, endpoint: str, example_request: str, publish: bool = False
    ):
        """
        Publishes the dynamically generated RPC debug tool HTML page to the datasite.
        """

        rendered_content = self.make_rpc_debug_page(endpoint, example_request)

        @self.app.get("/rpc-debug", response_class=HTMLResponse)
        def get_rpc_debug():
            return rendered_content

        if publish:
            # Generate the RPC debug page content dynamically
            js_sdk_path = (
                self.current_dir / "app_template" / "assets" / "js" / "syftbox-sdk.js"
            )
            js_rpc_debug_path = (
                self.current_dir / "app_template" / "assets" / "js" / "rpc-debug.js"
            )
            css_path = (
                self.current_dir / "app_template" / "assets" / "css" / "rpc-debug.css"
            )

            # Define the path in the datasite where the file should be published
            in_datasite_path = Path("public") / self.name / "rpc-debug.html"

            self.publish_contents(rendered_content, in_datasite_path)
            self.publish_file_path(
                js_sdk_path,
                f"public/{self.name}/js/syftbox-sdk.js",
            )
            self.publish_file_path(
                js_rpc_debug_path,
                f"public/{self.name}/js/rpc-debug.js",
            )
            self.publish_file_path(css_path, f"public/{self.name}/css/rpc-debug.css")
            datasite_url = f"{self.config.server_url}datasites/{self.client.email}"
            url = f"{datasite_url}/public/{self.name}/rpc-debug.html"
            print(f"🚀 Successfully Published rpc-debug to:\n🌐 URL: {url}")
