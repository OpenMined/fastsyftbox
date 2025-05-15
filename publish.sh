#!/bin/bash

rm -rf .venv
uv venv -p 3.12
uv pip install twine
uv run twine upload --repository fastsyftbox dist/*
