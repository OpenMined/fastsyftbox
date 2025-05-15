#!/bin/bash

rm -rf .venv
uv venv -p 3.12

rm -rf dist
uv pip install twine build bump2version
bump2version --config-file .bumpversion.cfg --allow-dirty patch

uv run python -m build
