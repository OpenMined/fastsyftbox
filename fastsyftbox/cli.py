import shutil
from pathlib import Path

import typer

from . import __version__

app = typer.Typer()


@app.command()
def create(
    subcommand: str = typer.Argument(..., help="Subcommand"),
    name: str = typer.Argument(..., help="Name of the app to create"),
):
    if subcommand != "app":
        typer.echo("Invalid subcommand. Use: fastsyftbox create app <APP_NAME>")
        raise typer.Exit(1)

    target_dir = Path(name)
    if target_dir.exists():
        typer.echo(f"Directory '{name}' already exists.")
        raise typer.Exit(1)

    template_dir = Path(__file__).parent / "app_template"
    shutil.copytree(template_dir, target_dir)

    typer.echo("--------------------------------------------------")
    typer.echo(f"FastSyftbox App '{name}' created successfully at ./{name}")
    typer.echo("--------------------------------------------------")
    typer.echo("Your app structure:")
    typer.echo(f"{name}/")
    typer.echo("├── run.sh            <-  entry point using 'uv' to manage packages")
    typer.echo("├── requirements.txt  <-  python requirements")
    typer.echo("└── app.py            <-  your fastapi and syftbox application")
    typer.echo("--------------------------------------------------")
    typer.echo(
        "You can optionally control the port by setting SYFTBOX_ASSIGNED_PORT=8080"
    )
    typer.echo("To get started, run the following commands:")
    typer.echo("--------------------------------------------------")
    typer.echo(f"cd {name}")
    typer.echo("./run.sh")
    typer.echo("Visit your app at: http://localhost:8080")


@app.command()
def version():
    """Print the current version of the application."""
    typer.echo(f"FastSyftbox version: {__version__}")


def main():
    app()


if __name__ == "__main__":
    main()
