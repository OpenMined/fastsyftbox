from pathlib import Path

import httpx

from fastsyftbox.transport import SyftFileSystemTransport

DEV_DEFAULT_OWNER_EMAIL = "guest@syftbox.com"


def default_dev_data_dir(app_name: str) -> Path:
    return Path(f"/tmp/{app_name}")


class SimpleRPCClient(httpx.Client):
    def __init__(
        self,
        *args,
        data_dir=None,
        app_owner=None,
        app_name=None,
        dev_mode=False,
        **kwargs,
    ):
        self.dev_mode = dev_mode
        self.app_owner = app_owner
        self.app_name = app_name

        if app_owner is None:
            if not dev_mode:
                raise ValueError("app_owner must be provided")
            else:
                app_owner = DEV_DEFAULT_OWNER_EMAIL

        if data_dir is None:
            if app_name is None:
                raise ValueError("data_dir or app_name must be provided")
            else:
                data_dir = default_dev_data_dir(app_name)
        data_dir = Path(data_dir)

        transport = SyftFileSystemTransport(
            app_name="data-syncer",
            app_owner=app_owner,
            data_dir=data_dir,
        )
        super().__init__(
            *args, transport=transport, base_url="syft://localhost", **kwargs
        )
