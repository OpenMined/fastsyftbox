from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from fastsyftbox import FastSyftBox

app_name = Path(__file__).resolve().parent.name

app = FastSyftBox(
    app_name=app_name,
    syftbox_endpoint_tags=[
        "syftbox"
    ],  # endpoints with this tag are also available via Syft RPC
    include_syft_openapi=True,  # Create OpenAPI endpoints for syft-rpc routes
)


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(
        content=f"<html><body><h1>Welcome to {app_name}</h1>"
        + f"{app.get_debug_urls()}"
        + "</body></html>"
    )


class MessageModel(BaseModel):
    message: str
    name: Optional[str] = None


# tags=syftbox means also available via Syft RPC
# syft://{datasite}/app_data/{app_name}/rpc/endpoint
@app.api_route(
    path="/hello", methods=["GET", "POST", "PUT", "DELETE"], tags=["syftbox"]
)
async def hello_handler(request: Request) -> MessageModel:
    try:
        print("> Request Method: ", request.method)
        print("> Request Body: ", await request.body())
        if request.query_params:
            print("> Query Params: ", request.query_params)
        print("> SyftBox URL: ", request.state.syftbox_url)

        if request.method == "POST":
            json_data = await request.json()
            msg = MessageModel(**json_data)
            name = msg.name
        else:
            name = request.query_params.get("name")

        response = MessageModel(message=f"Hi {name}", name="Bob")
        return response
    except Exception as e:
        print("Error", e)
        raise e


# Debug your Syft RPC endpoints in the browser
app.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
