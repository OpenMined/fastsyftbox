from fastapi import FastAPI
from syft_event import SyftEvents
from syft_core import SyftClientConfig, Client as SyftboxClient
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio


class Syftbox:
    def __init__(self, app: FastAPI, name: str = None, data_dir: str = "./data", config: SyftClientConfig = None):
        name = name if name is not None else Path(__file__).resolve().parent.name
        self.name = name
        self.app = app
        self.current_dir = Path(__file__).parent
        self.data_dir = Path(data_dir)

        # Load config + client
        self.config = config if config is not None else SyftClientConfig.load()
        self.client = SyftboxClient(self.config)

        # Setup event system
        self.box = SyftEvents(app_name=name)
        self.client.makedirs(self.client.datasite_path / "public" / name)
        self.data_dir.mkdir(parents=True, exist_ok=True)

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
