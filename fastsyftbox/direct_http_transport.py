import asyncio
import json
from pathlib import Path

import httpx

from fastsyftbox.sdk import ANONYMOUS_EMAIL, SyftBoxSDK, SyftTimeoutError


class DirectSyftboxTransport(httpx.BaseTransport):
    def __init__(
        self, app_owner: str, app_name: str, sender_email: str = ANONYMOUS_EMAIL
    ) -> None:
        self.app_owner = app_owner
        self.app_name = app_name
        self.sender_email = sender_email

    @classmethod
    def from_config(cls, config_path: Path):
        pass

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        sdk = SyftBoxSDK()
        if request.headers is None:
            headers = {}
        else:
            headers = dict(request.headers)

        headers.pop("content-length", None)

        body = json.loads(request.content) if request.content else {}

        try:
            response, _ = asyncio.run(
                sdk.syft_make_request(
                    f"syft://{self.app_owner}/app_data/{self.app_name}/rpc/{request.url.path}",
                    body=body,
                    headers=headers,
                    from_email=self.sender_email,
                )
            )
        except SyftTimeoutError as e:
            return httpx.Response(
                request=request,
                status_code=504,
                content=json.dumps({"error": "Timeout"}).encode("utf-8"),
            )

        response_headers = dict(response.headers)
        response_headers.pop("content-encoding", None)

        outer_response_body = (
            json.loads(response.content.decode("utf-8"))
            .get("data", {})
            .get("message", {})
        )
        response_content = json.dumps(outer_response_body.get("body", {})).encode(
            "utf-8"
        )

        syft_status_code = outer_response_body["status_code"]
        syft_headers = outer_response_body["headers"]

        http_response = httpx.Response(
            request=request,
            status_code=syft_status_code,
            headers=syft_headers,
            content=response_content,
        )

        return http_response

    def close(self) -> None:
        pass
