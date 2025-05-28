# %%

import json

from pydantic import BaseModel
from syft_core import Client as SyftboxClient
from syft_rpc import rpc

syftbox_client = SyftboxClient.load()

# %%

ping_url = rpc.make_url(
    datasite=syftbox_client.email,
    app_name="my_app",
    endpoint="ping",
)


class Ping(BaseModel):
    message: str


future = rpc.send(
    url=ping_url,
    method="POST",
    body=Ping(message="Ping!!"),
    client=syftbox_client,
)

response = future.wait()
response_json = response.json()
if response.status_code == 200:
    print(f"Ping successful: {response_json}")
else:
    print(f"Ping failed: {response.status_code} - {response.text}")

# %%

health_url = rpc.make_url(
    datasite=syftbox_client.email,
    app_name="my_app",
    endpoint="health",
)

future = rpc.send(
    url=health_url,
    method="GET",
    client=syftbox_client,
)

response = future.wait()
if response.status_code == 200:
    print(f"Health check passed: {response.json()}")
else:
    print(f"Health check failed: {response.status_code} - {response.text}")


# %%

openapi_url = rpc.make_url(
    datasite=syftbox_client.email,
    app_name="my_app",
    endpoint="syft/openapi.json",
)

future = rpc.send(
    url=openapi_url,
    method="GET",
    client=syftbox_client,
)

response = future.wait()
if response.status_code == 200:
    print("OpenAPI schema retrieved successfully:")
    print(json.dumps(response.json(), indent=2))
