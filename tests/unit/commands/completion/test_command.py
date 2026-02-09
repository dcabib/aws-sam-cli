"""Unit tests for the completion command."""

from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner

from samcli.commands.completion.command import cli, detect_shell, SUPPORTED_SHELLS


class TestDetectShell(TestCase):
    """Tests for the detect_shell function."""

    def test_detect_bash_shell(self):
        """Test detecting bash shell from SHELL environment variable."""
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = detect_shell()
            self.assertEqual(result, "bash")

    def test_detect_zsh_shell(self):
        """Test detecting zsh shell from SHELL environment variable."""
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            result = detect_shell()
            self.assertEqual(result, "zsh")

    def test_detect_fish_shell(self):
        """Test detecting fish shell from SHELL environment variable."""
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            result = detect_shell()
            self.assertEqual(result, "fish")

    def test_detect_shell_not_found(self):
        """Test returning None when shell is not detected."""
        with patch.dict("os.environ", {"SHELL": "/bin/sh"}):
            result = detect_shell()
            self.assertIsNone(result)

    def test_detect_shell_no_env_var(self):
        """Test returning None when SHELL environment variable is not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = detect_shell()
            self.assertIsNone(result)


class TestCompletionCommand(TestCase):
    """Tests for the completion CLI command."""

    def setUp(self):
        self.runner = CliRunner()

    def test_completion_bash_generates_script(self):
        """Test that bash completion generates a valid script."""
        result = self.runner.invoke(cli, ["bash"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("_sam_completion", result.output)
        self.assertIn("_SAM_COMPLETE=bash_complete", result.output)
        self.assertIn("complete -o nosort -F _sam_completion sam", result.output)

    def test_completion_zsh_generates_script(self):
        """Test that zsh completion generates a valid script."""
        result = self.runner.invoke(cli, ["zsh"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("#compdef sam", result.output)
        self.assertIn("_sam_completion", result.output)
        self.assertIn("_SAM_COMPLETE=zsh_complete", result.output)

    def test_completion_fish_generates_script(self):
        """Test that fish completion generates a valid script."""
        result = self.runner.invoke(cli, ["fish"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("_SAM_COMPLETE=fish_complete", result.output)
        self.assertIn("complete --no-files --command sam", result.output)

    def test_completion_autodetect_bash(self):
        """Test auto-detection of bash shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = self.runner.invoke(cli)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("_SAM_COMPLETE=bash_complete", result.output)

    def test_completion_autodetect_zsh(self):
        """Test auto-detection of zsh shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/zsh"}):
            result = self.runner.invoke(cli)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("#compdef sam", result.output)

    def test_completion_autodetect_fish(self):
        """Test auto-detection of fish shell."""
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            result = self.runner.invoke(cli)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("complete --no-files --command sam", result.output)

    def test_completion_autodetect_unknown_shell_fails(self):
        """Test that auto-detection fails gracefully for unsupported shells."""
        with patch.dict("os.environ", {"SHELL": "/bin/sh"}):
            result = self.runner.invoke(cli)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("Could not detect shell", result.output)

    def test_completion_invalid_shell_argument(self):
        """Test that invalid shell argument fails."""
        result = self.runner.invoke(cli, ["powershell"])
        self.assertEqual(result.exit_code, 2)
        self.assertIn("Invalid value for", result.output)

    def test_completion_unsupported_shell_class(self):
        """Test error handling when get_completion_class returns None."""
        with patch("samcli.commands.completion.command.get_completion_class", return_value=None):
            result = self.runner.invoke(cli, ["bash"])
            self.assertEqual(result.exit_code, 1)
            self.assertIn("Unsupported shell", result.output)

    def test_completion_help(self):
        """Test that help text is displayed correctly."""
        result = self.runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Generate shell completion scripts", result.output)
        self.assertIn("bash", result.output)
        self.assertIn("zsh", result.output)
        self.assertIn("fish", result.output)


class TestSupportedShells(TestCase):
    """Tests for the SUPPORTED_SHELLS constant."""

    def test_supported_shells_contains_expected_values(self):
        """Test that SUPPORTED_SHELLS contains bash, zsh, and fish."""
        self.assertIn("bash", SUPPORTED_SHELLS)
        self.assertIn("zsh", SUPPORTED_SHELLS)
        self.assertIn("fish", SUPPORTED_SHELLS)

    def test_supported_shells_length(self):
        """Test that SUPPORTED_SHELLS has exactly 3 values."""
        self.assertEqual(len(SUPPORTED_SHELLS), 3)
