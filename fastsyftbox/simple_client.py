from pathlib import Path

import httpx

from fastsyftbox.direct_http_transport import ANONYMOUS_EMAIL, DirectSyftboxTransport
from fastsyftbox.transport import SyftFileSystemTransport

DEV_DEFAULT_OWNER_EMAIL = "guest@syftbox.com"


def default_dev_data_dir(app_name: str) -> Path:
    return Path(f"/tmp/{app_name}")


class SimpleRPCClient(httpx.Client):
    def __init__(
        self,
        *args,
        app_owner=None,
        app_name=None,
        data_dir=None,
        sender_email=ANONYMOUS_EMAIL,
        use_local_transport=False,
        **kwargs,
    ):
        self.use_local_transport = use_local_transport
        self.app_owner = app_owner
        self.app_name = app_name
        self.data_dir = data_dir
        self.sender_email = sender_email

        if use_local_transport:
            if self.app_owner is None:
                self.app_owner = DEV_DEFAULT_OWNER_EMAIL

            if self.data_dir is None:
                if self.app_name is None:
                    raise ValueError("data_dir or app_name must be provided")
                else:
                    self.data_dir = default_dev_data_dir(self.app_name)

            self.data_dir = Path(self.data_dir)
            transport = SyftFileSystemTransport(
                app_name=self.app_name,
                app_owner=self.app_owner,
                data_dir=self.data_dir,
                sender_email=self.sender_email,
            )

        else:
            if app_owner is None or app_name is None:
                raise ValueError("app_owner and app_name must be provided")

            transport = DirectSyftboxTransport(
                app_owner=self.app_owner,
                app_name=self.app_name,
                sender_email=self.sender_email,
            )

        super().__init__(
            *args, transport=transport, base_url="syft://localhost", **kwargs
        )

    @classmethod
    def for_syftbox_transport(
        cls, app_owner, app_name, sender_email=ANONYMOUS_EMAIL, **kwargs
    ):
        return cls(
            app_owner=app_owner,
            app_name=app_name,
            use_local_transport=False,
            sender_email=sender_email,
            **kwargs,
        )

    @classmethod
    def for_local_transport(
        cls,
        app_owner=None,
        app_name=None,
        data_dir=None,
        sender_email=ANONYMOUS_EMAIL,
        **kwargs,
    ):
        return cls(
            app_owner=app_owner,
            app_name=app_name,
            data_dir=data_dir,
            use_local_transport=True,
            sender_email=sender_email,
            **kwargs,
        )
