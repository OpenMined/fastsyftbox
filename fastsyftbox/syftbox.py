from fastapi import FastAPI
from syft_event import SyftEvents
from syft_core import SyftClientConfig, Client as SyftboxClient
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio


class Syftbox:
    def __init__(self, app: FastAPI, name: str, data_dir: str = "./data", config: SyftClientConfig = None):
        self.name = name
        self.app = app

        # Load config + client
        self.config = config if config is not None else SyftClientConfig.load()
        self.client = SyftboxClient(self.config)

        # setup app data directory
        self.current_dir = Path(__file__).parent
        self.app_data_dir = Path(self.client.config.data_dir) / "private" / "app_data" /  name
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
