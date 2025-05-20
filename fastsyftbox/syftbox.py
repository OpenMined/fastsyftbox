import asyncio
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
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
        publish_path.mkdir(parents=True, exist_ok=True)

        shutil.copy2(local_path, publish_path)

    def publish_contents(self, file_contents: str, in_datasite_path: Path):
        publish_path = self.client.datasite_path / in_datasite_path
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        print("publish_path", publish_path, in_datasite_path)
        with open(publish_path, "w") as file:
            file.write(file_contents)
