# FastSyftBox Development Guide

## Project Overview
FastSyftBox is a Python library that combines FastAPI with SyftBox to build offline-first web applications with built-in RPC capabilities. It enables developers to create privacy-preserving applications that work locally without uploading data to the cloud.

## Key Features
- Local admin UIs with FastAPI
- Delay-tolerant UIs/APIs using SyftEvents
- HTTP over RPC with SyftBox
- Built-in JS SDK with fetch-compatible syntax
- Postman-style debug interface for RPC endpoints

## Development Commands

### Package Management
```bash
# Install dependencies (uses uv for fast package management)
uv sync

# Add new dependency
uv add <package>

# Build package
python -m build

# Publish to PyPI
./publish.sh
```

### Code Quality
```bash
# Run all linting and formatting checks
./lint.sh           # Auto-fix issues where possible
./lint.sh --check   # Check only, don't fix
./lint.sh --fix     # Explicitly fix issues
./lint.sh --strict  # Enable strict mypy checking

# Or run individual tools
ruff format .
ruff check . --fix
mypy fastsyftbox/

# Run tests with coverage
./test.sh

# Install dev dependencies only
uv sync --extra dev
```

### Testing & Development
```bash
# Create test app
uvx fastsyftbox create app test

# Run test app in hot-reload mode
cd test && ./run.sh

# Check version
uvx fastsyftbox version
```

## Project Structure
```
fastsyftbox/
   fastsyftbox/           # Main package
      __init__.py        # Package exports
      cli.py             # CLI interface (Typer)
      fastsyftbox.py     # Core FastSyftBox class
      http_bridge.py     # HTTP-RPC bridge
      app_template/      # Template for new apps
          app.py         # Sample FastAPI app
          assets/        # Frontend assets (JS/CSS/HTML)
          requirements.txt
          run.sh         # Development server script
   img/                   # Documentation images
   pyproject.toml         # Project configuration
   README.md             # Main documentation
```

## Core Components

### FastSyftBox Class (`fastsyftbox.py`)
- Extends FastAPI with SyftBox integration
- Manages HTTP-RPC bridge lifecycle
- Auto-discovers Syft-enabled routes
- Generates OpenAPI specs for RPC endpoints

### HTTP Bridge (`http_bridge.py`)
- Translates HTTP requests to SyftBox RPC
- Handles async request/response patterns
- Manages connection pooling

### CLI (`cli.py`)
- Built with Typer for command-line interface
- Supports app creation and version commands
- Template-based app scaffolding

## Development Patterns

### Adding New Features
1. Update core classes in `fastsyftbox/`
2. Add CLI commands in `cli.py` if needed
3. Update app template if relevant
4. Add examples to README.md
5. Test with sample apps

### RPC Endpoint Development
```python
# Tag endpoints for SyftBox RPC exposure
@app.post("/endpoint", tags=["syftbox"])
def my_endpoint(request: MyModel):
    return response

# Enable debug tool for testing
app.enable_debug_tool(
    endpoint="/endpoint",
    example_request=str(MyModel(...).model_dump_json()),
    publish=True
)
```

### Frontend Integration
- Use `syftFetch()` instead of `fetch()` for RPC calls
- Assets in `app_template/assets/` are copied to new apps
- Debug tool provides interactive RPC testing

## Configuration

### Ruff (Linting/Formatting)
- Line length: 88 characters
- Enabled rules: E (pycodestyle errors), F (pyflakes), I (isort)
- Auto-fix enabled for all rules

### Dependencies
- FastAPI e0.115.12 (web framework)
- Uvicorn e0.34.2 (ASGI server)
- syft-event e0.2.1 (event handling)
- syft-core e0.2.3 (SyftBox integration)
- Typer e0.4.0 (CLI framework)
- HTTPX e0.28.1 (HTTP client)

## Common Tasks

### Creating New CLI Commands
Add to `cli.py` using Typer decorators:
```python
@app.command()
def new_command(arg: str = typer.Argument(help="Description")):
    """Command description."""
    pass
```

### Updating App Template
Modify files in `fastsyftbox/app_template/` - these are copied when users run `fastsyftbox create app`.

### Adding Frontend Assets
Place files in `fastsyftbox/app_template/assets/` with proper subdirectories:
- `js/` for JavaScript files
- `css/` for stylesheets  
- `html/` for templates

## Debugging

### RPC Debug Tool
Access at: `http://localhost:${SYFTBOX_ASSIGNED_PORT}/rpc-debug`
- Construct syft:// URLs
- Configure custom headers
- View real-time responses

### Local Development
1. Create test app: `uvx fastsyftbox create app testapp`
2. Navigate: `cd testapp`
3. Start with hot-reload: `./run.sh`
4. Visit: `http://localhost:${SYFTBOX_ASSIGNED_PORT}`

## Best Practices

### Code Style
- Follow Ruff formatting (88 char lines)
- Use type hints throughout
- Async/await for I/O operations
- Pydantic models for data validation

### Architecture
- Keep core logic in main package
- Use dependency injection patterns
- Separate concerns (HTTP, RPC, CLI)
- Template-based extensibility

### Testing
- Test CLI commands with different scenarios
- Verify RPC bridge functionality
- Test app template generation
- Validate OpenAPI generation

#### Test Structure
```
tests/
├── __init__.py              # Test package
├── conftest.py              # Pytest fixtures
├── test_fastsyftbox.py      # Core FastSyftBox tests
├── test_cli.py              # CLI command tests
├── test_http_bridge.py      # HTTP-RPC bridge tests
└── test_app_template.py     # Template generation tests
```

#### Running Tests
```bash
# Run all tests with coverage
./test.sh

# Run specific test file
uv run pytest tests/test_cli.py -v

# Run tests with specific pattern
uv run pytest -k "test_cli" -v
```

## Release Process
1. Update version in `pyproject.toml`
2. Run quality checks: `ruff format . && ruff check .`
3. Build: `python -m build`
4. Publish: `./publish.sh`
5. Tag release in git

## Useful Links
- [SyftBox Platform](https://github.com/OpenMined/syftbox)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Example Apps](https://github.com/madhavajay/youtube-wrapped)