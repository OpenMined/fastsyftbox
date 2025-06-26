import asyncio
import json
from pathlib import Path
import time
from typing import Optional, Union
import urllib.parse
import uuid

import httpx


class SyftError(Exception):
    pass


CONSTANTS = {
    "STORAGE_KEY": "syftbox-requests",
    "DEFAULT_SERVER_URL": "https://syftbox.net/",
    "DEFAULT_POLLING_INTERVAL": 3000,
    "DEFAULT_MAX_POLL_ATTEMPTS": 20,
    "DEFAULT_TIMEOUT": 5000,
    "MAX_BACKOFF_DELAY": 30000,
}

ANONYMOUS_EMAIL = "guest@syft.org"


class SyftRequest:
    def __init__(self, id: str, request_data: dict):
        self.id = id
        self.request_data = request_data
        self.status = "PENDING"
        self.timestamp = time.time()
        self.callbacks = []
        self.response_data = None
        self.error = None
        self.poll_timer = None
        self.poll_attempt = 0
        self.max_poll_attempts = CONSTANTS["DEFAULT_MAX_POLL_ATTEMPTS"]

    def update_status(self, status: str, data: dict):
        self.status = status
        if status == "SUCCESS":
            self.response_data = data
            self.poll_attempt = 0
        elif status == "ERROR":
            self.error = data
            self.poll_attempt = 0
        elif status == "POLLING":
            if not self.id or data:
                self.id = data

    def update_polling_progress(self, attempt: int, max_attempts: int):
        self.poll_attempt = attempt
        self.max_poll_attempts = max_attempts
        self.timestamp = time.time()


class PollingManager:
    def __init__(self, config: dict):
        self.interval = config.get("pollingInterval", 1000)
        self.max_attempts = config.get("maxPollAttempts", 30)

    async def poll(self, poll_fn, on_progress=None):
        attempt = 0
        stop = False
        while attempt < self.max_attempts and not stop:
            try:
                response = await poll_fn()
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") != "pending":
                        return response
                elif (
                    response.status_code == 500
                    and response.json().get("error")
                    == "No response exists. Polling timed out"
                ):
                    pass
                elif response.status_code == 404:
                    return response
                else:
                    return response

                if not stop:
                    await self._delay(self._get_backoff_delay(attempt))
                attempt += 1
                if on_progress:
                    on_progress(attempt, self.max_attempts)
            except Exception as error:
                if attempt == self.max_attempts - 1:
                    raise error

        raise SyftError("Polling timeout", "POLLING_TIMEOUT")

    def _get_backoff_delay(self, attempt: int) -> int:
        return min(1000 * (2**attempt), 30000)  # Max 30 seconds

    async def _delay(self, milliseconds: int):
        import asyncio

        await asyncio.sleep(milliseconds / 1000)


class SyftBoxSDK:
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            config = {}
        self.config = config
        self.server_url = config.get("serverUrl", CONSTANTS["DEFAULT_SERVER_URL"])
        self.polling_manager = PollingManager(config)

    async def syft_fetch(self, syft_url: str, options: Optional[dict] = None):
        httpx_res, id = await self.syft_make_request(syft_url, options)
        return self.parse_httpx_res(httpx_res, id)

    async def syft_make_request(
        self,
        syft_url: str,
        body: Optional[dict] = None,
        from_email: str = ANONYMOUS_EMAIL,
        headers: Optional[dict] = None,
        method: str = "POST",
    ):
        if headers is None:
            headers = {}
        if body is None:
            body = {}

        headers["x-syft-from"] = from_email
        headers["x-syft-method"] = method
        headers["x-syft-body"] = json.dumps(body).encode("utf-8")

        request_data = {
            "syftUrl": syft_url,
            "fromEmail": from_email,
            "method": method,
            "headers": headers,
            "body": body,
        }
        id = str(uuid.uuid4())
        request = SyftRequest(id, request_data)

        httpx_res = await self.send_request(request)
        return httpx_res, id

    def parse_httpx_res(self, response: httpx.Response, request_id: str) -> dict:
        if not response.is_success:
            try:
                body = response.json()
            except:
                body = {}

            if (
                response.status_code == 500
                and body.get("error") == "No response exists. Polling timed out"
            ):
                return None
            elif response.status_code == 404:
                return {
                    "status": "ERROR",
                    "message": body.get("message", "No request found."),
                    "request_id": request_id,
                }
            else:
                raise SyftError(
                    f"Polling failed: {response.status_code}", "POLLING_ERROR"
                )
        return {
            "status_code": response.status_code,
            "headers": response.headers,
            "body": response.json(),
        }

    async def send_request(self, request: SyftRequest):
        syft_url = request.request_data["syftUrl"]
        from_email = request.request_data["fromEmail"]
        method = request.request_data["method"]
        headers = request.request_data["headers"]
        body = request.request_data["body"]

        combined_headers = {
            "Content-Type": "application/json",
            "x-syft-from": from_email,
            "timeout": str(self.config.get("timeout", CONSTANTS["DEFAULT_TIMEOUT"])),
            **headers,
        }

        try:
            raw_param = (
                f"&x-syft-raw={headers.get('x-syft-raw', '')}"
                if headers.get("x-syft-raw")
                else ""
            )
            msg_url = (
                f"{self.server_url}api/v1/send/msg?"
                f"x-syft-from={from_email}&"
                f"x-syft-url={urllib.parse.quote(syft_url)}"
                f"{raw_param}"
            )

            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=msg_url,
                    headers=combined_headers,
                    content=json.dumps(body).encode("utf-8"),
                )
            if response.status_code == 202:
                response_body = response.json()
                print("initial response_body", response_body)
                if not response_body.get("request_id"):
                    raise SyftError(
                        "Accepted but missing request_id", "INVALID_RESPONSE"
                    )

                request.update_status("POLLING", response_body["request_id"])
                # for key, value in response.headers.items():
                #     print(f"Header: {key} = {value}")

                poll_url = response_body.get("data", {}).get("poll_url")
                location_header = response.headers.get("Location")

                poll_result = await self.poll_for_response(
                    {
                        "requestId": response_body["request_id"],
                        "pollUrlPath": poll_url or location_header,
                        "request": request,
                    }
                )

                request.update_status("SUCCESS", poll_result)
                return poll_result

            if response.is_success:
                response_data = response.json()
                request.update_status("SUCCESS", response_data)
                return response

            return response
        except Exception as error:
            request.update_status("ERROR", str(error))
            raise error

    async def poll_for_response(self, poll_data):
        """Poll for response from the server."""
        request_id = poll_data["requestId"]
        poll_url_path = poll_data["pollUrlPath"]
        request = poll_data["request"]

        poll_url = f"{self.server_url}{poll_url_path.lstrip('/')}"

        return await self.polling_manager.poll(
            poll_fn=lambda: self._poll_request(poll_url, request_id),
            on_progress=lambda attempt, max_attempts: request.update_polling_progress(
                attempt, max_attempts
            ),
        )

    async def _poll_request(self, poll_url, request_id):
        """Make a single poll request."""
        print("poll url", poll_url)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                poll_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

        return response


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

        response, _ = asyncio.run(
            sdk.syft_make_request(
                f"syft://{self.app_owner}/app_data/{self.app_name}/rpc/{request.url.path}",
                body=body,
                headers=headers,
                from_email=self.sender_email,
            )
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
