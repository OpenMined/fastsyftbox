from fastapi import FastAPI
from fastsyftbox import Syftbox
from pathlib import Path
app = FastAPI()

# Build your local UI available on http://localhost:{SYFTBOX_ASSIGNED_PORT}/
@app.get("/")
def read_root():
    return {"message": "Welcome to fastsyftbox"}

syftbox = Syftbox(
    app=app,
    name=Path(__file__).resolve().parent.name
)

# Build your DTN RPC endpoints available on syft://{datasite}/app_data/{app_name}/rpc/ping
@syftbox.on_request("/ping")
def ping_handler(ping):
    return {"message": "pong"}
