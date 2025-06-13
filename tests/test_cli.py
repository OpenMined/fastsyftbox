"""Tests for FastSyftBox CLI functionality."""

from unittest.mock import patch

from typer.testing import CliRunner

from fastsyftbox.cli import app, main


class TestCLI:
    """Test cases for CLI functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_version_command(self):
        """Test version command output."""
        result = self.runner.invoke(app, ["version"])
        assert result.exit_code == 0
        # Import version from the package
        from fastsyftbox import __version__

        assert __version__ in result.stdout
        assert "FastSyftbox version:" in result.stdout

    @patch("fastsyftbox.cli.shutil.copytree")
    @patch("fastsyftbox.cli.Path.exists")
    def test_create_app_command(self, mock_exists, mock_copytree):
        """Test create app command."""
        mock_exists.return_value = False

        result = self.runner.invoke(app, ["create", "app", "test_app"])

        assert result.exit_code == 0
        assert "created successfully" in result.stdout
        assert "test_app" in result.stdout
        mock_copytree.assert_called_once()

    @patch("fastsyftbox.cli.Path.exists")
    def test_create_app_existing_directory(self, mock_exists):
        """Test create app command with existing directory."""
        mock_exists.return_value = True

        result = self.runner.invoke(app, ["create", "app", "existing_app"])

        assert result.exit_code == 1
        assert "already exists" in result.stdout

    def test_main_function(self):
        """Test main function calls typer app."""
        with patch("fastsyftbox.cli.app") as mock_app:
            main()
            mock_app.assert_called_once()

    def test_help_command(self):
        """Test CLI help output."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Commands" in result.stdout
        assert "create" in result.stdout
        assert "version" in result.stdout

    def test_create_invalid_subcommand(self):
        """Test create command with invalid subcommand."""
        result = self.runner.invoke(app, ["create", "invalid", "test_app"])

        assert result.exit_code == 1
        assert "Invalid subcommand" in result.stdout
        assert "fastsyftbox create app" in result.stdout

    @patch("fastsyftbox.cli.shutil.copytree")
    @patch("fastsyftbox.cli.Path.exists")
    def test_create_app_command_with_path_arguments(self, mock_exists, mock_copytree):
        """Test create app command verifies correct paths are used."""
        mock_exists.return_value = False

        result = self.runner.invoke(app, ["create", "app", "my_test_app"])

        assert result.exit_code == 0
        # Verify copytree was called with the correct arguments
        assert mock_copytree.call_count == 1
        call_args = mock_copytree.call_args[0]
        # First argument should be the template directory
        template_path = call_args[0]
        assert "app_template" in str(template_path)
        # Second argument should be the target directory
        target_path = call_args[1]
        assert str(target_path) == "my_test_app"
