"""Tests for app template functionality."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from fastsyftbox.cli import app as cli_app


class TestAppTemplate:
    """Test cases for app template generation."""

    @pytest.fixture
    def template_dir(self):
        """Fixture providing path to app template directory."""
        return Path(__file__).parent.parent / "fastsyftbox" / "app_template"

    @pytest.fixture
    def temp_app_dir(self):
        """Fixture providing temporary directory for app creation tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_template_structure_exists(self, template_dir):
        """Test that app template directory structure exists."""
        assert template_dir.exists()
        assert (template_dir / "app.py").exists()
        assert (template_dir / "requirements.txt").exists()
        assert (template_dir / "run.sh").exists()
        assert (template_dir / "assets").exists()

    def test_app_creation_via_cli(self, temp_app_dir):
        """Test app creation through CLI command."""
        runner = CliRunner()
        app_name = "test_app"

        with runner.isolated_filesystem(temp_dir=str(temp_app_dir)):
            # Test create app command
            result = runner.invoke(cli_app, ["create", "app", app_name])

            assert result.exit_code == 0
            assert f"FastSyftbox App '{app_name}' created successfully" in result.output

            # Verify created app structure
            app_dir = Path(app_name)
            assert app_dir.exists()
            assert (app_dir / "app.py").exists()
            assert (app_dir / "requirements.txt").exists()
            assert (app_dir / "run.sh").exists()
            assert (app_dir / "assets").exists()

    def test_created_app_integrity(self, temp_app_dir):
        """Test that created app maintains template integrity."""
        runner = CliRunner()
        app_name = "integrity_test_app"

        with runner.isolated_filesystem(temp_dir=str(temp_app_dir)):
            result = runner.invoke(cli_app, ["create", "app", app_name])
            assert result.exit_code == 0

            app_dir = Path(app_name)

            # Test requirements.txt
            requirements = (app_dir / "requirements.txt").read_text()
            assert "fastsyftbox" in requirements

            # Test run.sh permissions
            run_sh = app_dir / "run.sh"
            file_stat = run_sh.stat()
            assert file_stat.st_mode & stat.S_IEXEC

    def test_template_variable_substitution(self, template_dir):
        """Test template variable substitution in debug tool."""
        from fastsyftbox.fastsyftbox import FastSyftBox

        # Mock the SyftClientConfig and Client
        with (
            patch("fastsyftbox.fastsyftbox.SyftClientConfig") as mock_config_class,
            patch("fastsyftbox.fastsyftbox.SyftboxClient") as mock_client_class,
        ):
            mock_config = MagicMock()
            mock_config.server_url = "https://test.syftbox.com/"
            mock_config_class.load.return_value = mock_config

            mock_client = MagicMock()
            mock_client.email = "test@example.com"
            mock_client_class.return_value = mock_client

            app = FastSyftBox(app_name="test_app")

            # Test debug page generation
            debug_content = app.make_rpc_debug_page("/test", '"test_request"')

            # Verify variable substitution
            assert "https://test.syftbox.com/" in debug_content
            assert "test@example.com" in debug_content
            assert "test_app" in debug_content
            assert "/test" in debug_content
            assert "test_request" in debug_content

            # Verify no template placeholders remain
            template_vars = [
                "{{ server_url }}",
                "{{ from_email }}",
                "{{ to_email }}",
                "{{ app_name }}",
                "{{ app_endpoint }}",
                "{{ request_body }}",
            ]

            for var in template_vars:
                assert var not in debug_content, (
                    f"Template variable not substituted: {var}"
                )

    def test_cli_error_handling(self, temp_app_dir):
        """Test CLI error handling for invalid commands and existing directories."""
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(temp_app_dir)):
            # Test invalid subcommand
            result = runner.invoke(cli_app, ["create", "invalid", "test_app"])
            assert result.exit_code == 1
            assert "Invalid subcommand" in result.output

            # Create a directory first
            os.makedirs("existing_app")

            # Test existing directory
            result = runner.invoke(cli_app, ["create", "app", "existing_app"])
            assert result.exit_code == 1
            assert "already exists" in result.output
