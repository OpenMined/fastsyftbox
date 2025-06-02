from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse
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
    name: str | None = None


# tags=syftbox means also available via Syft RPC
# syft://{datasite}/app_data/{app_name}/rpc/endpoint
@app.post("/hello", tags=["syftbox"])
def hello_handler(request: MessageModel) -> JSONResponse:
    print("got request", request)
    response = MessageModel(message=f"Hi {request.name}", name="Bob")
    return response.model_dump_json()


# Debug your Syft RPC endpoints in the browser
app.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
