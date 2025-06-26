from pathlib import Path
from typing import Union

import httpx
from httpx import BaseTransport, Request, Response
from syft_core import Client as SyftBoxClient
from syft_core import SyftBoxURL, SyftClientConfig
from syft_rpc import rpc


def _read_content(obj: Union[Request, Response]) -> bytes:
    """Read content from a request or response object safely."""
    try:
        return obj.content
    except (httpx.RequestNotRead, httpx.ResponseNotRead):
        return obj.read()


class SyftFileSystemTransport(BaseTransport):
    def __init__(
        self,
        app_owner: str,
        app_name: str,
        data_dir: Path,
        sender_email: str = "guest@syftbox.com",
    ) -> None:
        self.app_owner = app_owner
        self.app_name = app_name
        self.data_dir = data_dir
        self.sender_email = sender_email

        self.app_dir = self.data_dir / app_owner / "app_data" / app_name
        self.rpc_dir = self.app_dir / "rpc"

    @classmethod
    def from_config(cls, config_path: Path) -> "SyftFileSystemTransport":
        pass

    def handle_request(self, request: Request) -> Response:
        body = _read_content(request)

        config = SyftClientConfig(
            client_url=8002,  # does not matter
            path="",  # does not matter
            data_dir=self.data_dir,
            email=self.sender_email,
        )

        syftbox_client = SyftBoxClient(
            conf=config,
        )
        expiry = "5s"

        syft_url = SyftBoxURL(
            f"syft://{self.app_owner}/app_data/{self.app_name}/rpc/{request.url.path}"
        )

        future = rpc.send(
            url=syft_url,
            method=request.method,
            body=body,
            headers=dict(request.headers.items()),
            cache=False,
            client=syftbox_client,
        )

        timeout_seconds = float(rpc.parse_duration(expiry).seconds)
        response = future.wait(timeout=timeout_seconds)
        http_response = httpx.Response(
            status_code=response.status_code.value,
            headers=response.headers,
            content=response.body,
        )

        return http_response

    def close(self) -> None:
        pass
