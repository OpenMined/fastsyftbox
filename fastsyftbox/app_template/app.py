import json
from pathlib import Path

import jinja2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig

from fastsyftbox.syftbox import Syftbox

config = SyftClientConfig.load()
client = SyftboxClient(config)

current_dir = Path(__file__).parent

app = FastAPI()
app.mount("/js", StaticFiles(directory=current_dir / "assets" / "js"), name="js")

app_name = "fastsyftbox"
endpoint = "/hello"


@app.get("/", response_class=HTMLResponse)
def read_root():
    print("client.email", client.email, client)
    return make_rpc_debug_page()


def make_sdk_page():
    sdk_page_path = current_dir / "assets" / "js-sdk.html"
    with open(sdk_page_path, "r") as file:
        sdk_page_content = file.read()

    return sdk_page_content


def make_rpc_debug_page():
    ping_page_path = current_dir / "assets" / "rpc-debug.html"
    with open(ping_page_path, "r") as file:
        ping_page_content = file.read()

    template = jinja2.Template(ping_page_content)
    content = {}
    # content = {
    #     "datasite_email": client.email,
    #     "app_name": app_name,
    #     "server_url": config.server_url,
    #     "endpoint": endpoint,
    #     "syft_url": f"syft://{client.email}/app_data/{app_name}/rpc{endpoint}",
    #     "body": MessageModel(message="Hello!", name="Alice").model_dump_json(),
    #     "from_email": "guest",
    # }
    rendered_content = template.render(**content)

    return rendered_content


def make_ping_page():
    ping_page_path = current_dir / "assets" / "ping.html"
    with open(ping_page_path, "r") as file:
        ping_page_content = file.read()

    template = jinja2.Template(ping_page_content)
    content = {
        "datasite_email": client.email,
        "app_name": app_name,
        "server_url": config.server_url,
        "endpoint": endpoint,
        "syft_url": f"syft://{client.email}/app_data/{app_name}/rpc{endpoint}",
        "body": MessageModel(message="Hello!", name="Alice").model_dump_json(),
        "from_email": "guest",
    }
    rendered_content = template.render(**content)

    return rendered_content


class MessageModel(BaseModel):
    message: str
    name: str | None = None


# Serve static files from the assets/images directory
# app.mount(
#     "/images", StaticFiles(directory=current_dir / "assets" / "images"), name="images"
# )


# app_name = Path(__file__).resolve().parent.name


def get_file_contents_of_syftbox_sdk_js():
    file_path = current_dir / "assets" / "js" / "syftbox-sdk.js"
    try:
        with open(file_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None


syftbox = Syftbox(app=app, name=app_name)
syftbox.publish_debug_tool()


@syftbox.on_request(endpoint)
def ping_handler(request: str):
    print("ping", request, type(request))
    request_json = json.loads(request)
    print("request_json", request_json, type(request_json))
    try:
        message = MessageModel(**request_json)
    except ValidationError as e:
        print(f"Validation error: {e}")
        return MessageModel(message="Invalid request format")
    response = MessageModel(message=f"Hi {message.name}")
    print("response", response, type(response))
    return response.model_dump_json()
