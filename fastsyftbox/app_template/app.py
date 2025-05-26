from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig

from fastsyftbox.syftbox import Syftbox

config = SyftClientConfig.load()
client = SyftboxClient(config)

current_dir = Path(__file__).parent

app = FastAPI()
app.mount("/js", StaticFiles(directory=current_dir / "assets" / "js"), name="js")
app.mount("/css", StaticFiles(directory=current_dir / "assets" / "css"), name="css")

app_name = "fastsyftbox"


@app.get("/", response_class=HTMLResponse)
def root():
    return "ok"


syftbox = Syftbox(app=app, name=app_name)


class MessageModel(BaseModel):
    message: str
    name: str | None = None


@syftbox.on_request("/hello")
def hello_handler(request: MessageModel):
    response = MessageModel(message=f"Hi {request.name}")
    return response.model_dump_json()


syftbox.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
