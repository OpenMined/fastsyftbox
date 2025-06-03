#!/bin/bash

rm -rf .venv

uv venv -p 3.12 .venv
uv pip install -r requirements.txt
# Set default port if not provided
SYFTBOX_ASSIGNED_PORT=${SYFTBOX_ASSIGNED_PORT:-8080}
uv run uvicorn app:app --reload --host 0.0.0.0 --port $SYFTBOX_ASSIGNED_PORT --workers 1
