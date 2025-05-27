from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from fastsyftbox.syftbox import Syftbox

app_name = Path(__file__).resolve().parent.name
app = FastAPI(title=app_name)
syftbox = Syftbox(app=app, name=app_name)


# Build your local UI available on
# http://localhost:{SYFTBOX_ASSIGNED_PORT}
@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(
        content=f"<html><body><h1>Welcome to {app_name}</h1>"
        + f"{syftbox.get_debug_urls()}"
        + "</body></html>"
    )


class MessageModel(BaseModel):
    message: str
    name: str | None = None


# Build your DTN RPC endpoints available on
# syft://{datasite}/app_data/{app_name}/rpc/endpoint
@syftbox.on_request("/hello")
def hello_handler(request: MessageModel):
    response = MessageModel(message=f"Hi {request.name}", name="Bob")
    return response.model_dump_json()


# Debug your RPC endpoints in the browser
syftbox.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
