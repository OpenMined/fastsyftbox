<h1 style="border: none; margin-bottom: 0;">fastsyftbox</h1>
<a href="https://syftbox.net/" target="_blank">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="img/mwsyftbox_white_on.png">
    <img alt="Logo" src="img/mwsyftbox_black_on.png" width="200px" align="right" />
  </picture>
</a>

[![PyPI - Version](https://img.shields.io/pypi/v/fastsyftbox)](https://pypi.org/project/fastsyftbox/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastsyftbox)](https://pypi.org/project/fastsyftbox/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/fastsyftbox)](https://pypi.org/project/fastsyftbox/)
[![Tests](https://github.com/OpenMined/fastsyftbox/actions/workflows/pr-tests.yml/badge.svg)](https://github.com/OpenMined/fastsyftbox/actions/workflows/pr-tests.yml)
[![License](https://img.shields.io/github/license/OpenMined/fastsyftbox)](https://github.com/OpenMined/fastsyftbox/blob/main/LICENSE)
[![MadeWith](https://img.shields.io/badge/MadeWith-SyftBox-blue)](https://syftbox.net/)

<br />

## Build offline-first Python apps with FastAPI and SyftBox — FAST.

## 🚀 Features

- Build **local admin UIs** with [FastAPI](https://fastapi.tiangolo.com/).
- Build **delay-tolerant UIs/APIs** using SyftEvents.
- Keep private data offline with **SyftBox HTTP over RPC**.
- Builtin JS SDK with `fetch` compatible syntax
- Debug APIs with a built-in **Postman-style interface**.

---

## 🔧 Purpose

How can you build a web app that runs on your **own device**, without uploading data to the cloud?

With SyftBox, you can:
- Run a webserver anywhere that can go offline and keep functioning when it comes back online.
- Access your data **even when offline** or when your laptop lid is closed.

---

## ⚡ Quick Start

Install with [uv](https://github.com/astral-sh/uv) and create your app:
```bash
uvx fastsyftbox version
uvx fastsyftbox create app test
```

To start in hot-reloading more:
```
cd test
./run.sh
```

This generates a sample FastAPI app in `app.py`:
```python


app = FastSyftBox(
    app_name=app_name,
    syftbox_endpoint_tags=[
        "syftbox"
    ],  # endpoints with this tag are also available via Syft RPC
    include_syft_openapi=True,  # Create OpenAPI endpoints for syft-rpc routes
)


# normal fastapi
@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse("<html><body><h1>Welcome to {app_name}</h1>")


# build a model with pydantic
class MessageModel(BaseModel):
    message: str
    name: str | None = None

# make syftbox rpc endpoints easily
# syft://{datasite}/app_data/{app_name}/rpc/hello
@app.post("/hello", tags=["syftbox"])
def hello_handler(request: MessageModel):
    print("got request", request)
    response = MessageModel(message=f"Hi {request.name}", name="Bob")
    return response.model_dump_json()

# Debug your RPC endpoints in the browser
app.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
```

## HTTP / JS

Vanilla JS fetch:
```js
const url = "http://somewebsite.com/api"
const request = await fetch(url, {
    method: 'POST',
    headers,
    body
});
```

Becomes syftFetch:
```js
const syftUrl = "syft://madhava@openmined.org/app_data/fastsyftbox/rpc/hello"
const request = await syftFetch(syftUrl, {
    method: 'POST',
    headers,
    body
});
```

Under the hood:
- Translates to the correct HTTP request
- Adds `syft-x` headers
- Waits for queued response
- Polls future until completed


## What is SyftBox?
<a href="https://syftbox.net/" target="_blank"><img src="img/syftbox_icon.png" style="width:200px; max-width: 200px;" align="right" target="_blank" /></a>
SyftBox is a new platform for building privacy-preserving applications and experiences that work over the internet without uploading your data. Instead of sending your data to a server, SyftBox lets you run powerful AI and analytics locally or in trusted environments, so your personal information stays private and secure.

<a href="https://syftbox.net/" target="_blank">Read more about SyftBox here</a>
<div style="clear: both;"></div>

## 🧱 Your Dependencies
Add any Python dependencies to `requirements.txt` and `run.sh` will install them fresh every run.


## 🧪 RPC Debug Tool

Its like Postman but for SyftBox RPC.

A built-in HTML/JS tool helps you debug your HTTP over RPC endpoints.
To enable:

```python
app.enable_debug_tool(
    endpoint="/hello",
    example_request=str(MessageModel(message="Hello!", name="Alice").model_dump_json()),
    publish=True,
)
```

### 🧭 Construct syft:// RPC URLs
![Debug Tool Screenshot](img/debug_1.png)

### 🎯 Configure custom headers
![Debug Tool Screenshot](img/debug_2.png)

### 🔍 View real-time responses
![Debug Tool Screenshot](img/debug_3.png)

Then visit either:
http://localhost:${SYFTBOX_ASSIGNED_PORT}/rpc-debug
or if you have publish=True
https://syftbox.net/datasites/{{ email }}/public/{{ app_name }}/rpc-debug.html


## 📥 SyftBox App Install via GitHub
```bash
syftbox app install GITHUB_URL
```
This executes run.sh and binds your app to a random port:
http://localhost:${SYFTBOX_ASSIGNED_PORT}


## 📚 Example `fastsyftbox` Apps
- 🎬 <a href="https://github.com/madhavajay/youtube-wrapped" target="_blank">YouTube Wrapped</a>
