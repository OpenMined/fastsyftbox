from fastapi import FastAPI
from fastsyftbox import Syftbox

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from app.py"}


syftbox = Syftbox(app=app)

@syftbox.on_request("/ping")
def ping_handler(ping):
    return f"{ping} pong"
