"""
Unit tests for debugger utilities.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from samcli.lib.utils.debugger import (
    ARCH_LINUX_AMD64,
    ARCH_LINUX_ARM64,
    DEBUGGER_VSDBG,
    DebuggerArchitectureMismatch,
    DebuggerDownloadError,
    _architecture_to_docker_platform,
    _architecture_to_linux_runtime,
    _get_debugger_cache_dir,
    clear_debugger_cache,
    detect_binary_architecture,
    download_vsdbg,
    get_or_download_debugger,
    get_vsdbg_cache_path,
    is_vsdbg_cached,
    validate_debugger_architecture,
)
from samcli.lib.utils.architecture import ARM64, X86_64


class TestDetectBinaryArchitecture:
    """Tests for detect_binary_architecture function."""

    def test_detects_x86_64_binary(self, tmp_path):
        """Test detection of x86_64 binary."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="/path/to/binary: ELF 64-bit LSB executable, x86-64, version 1 (SYSV)"
            )
            result = detect_binary_architecture(str(binary_path))

        assert result == X86_64

    def test_detects_amd64_binary(self, tmp_path):
        """Test detection of amd64 binary (alternative naming)."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="/path/to/binary: executable amd64")
            result = detect_binary_architecture(str(binary_path))

        assert result == X86_64

    def test_detects_arm64_binary(self, tmp_path):
        """Test detection of ARM64 binary."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="/path/to/binary: ELF 64-bit LSB executable, ARM aarch64"
            )
            result = detect_binary_architecture(str(binary_path))

        assert result == ARM64

    def test_detects_aarch64_binary(self, tmp_path):
        """Test detection of aarch64 binary (alternative naming)."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="/path/to/binary: aarch64")
            result = detect_binary_architecture(str(binary_path))

        assert result == ARM64

    def test_returns_none_for_nonexistent_path(self):
        """Test returns None for non-existent path."""
        result = detect_binary_architecture("/nonexistent/path/binary")
        assert result is None

    def test_returns_none_for_unknown_architecture(self, tmp_path):
        """Test returns None for unknown architecture."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="/path/to/binary: unknown format")
            result = detect_binary_architecture(str(binary_path))

        assert result is None

    def test_handles_timeout(self, tmp_path):
        """Test handles subprocess timeout gracefully."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="file", timeout=10)
            result = detect_binary_architecture(str(binary_path))

        assert result is None

    def test_handles_file_command_not_found(self, tmp_path):
        """Test handles 'file' command not found."""
        binary_path = tmp_path / "binary"
        binary_path.write_bytes(b"fake binary")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("file not found")
            result = detect_binary_architecture(str(binary_path))

        assert result is None


class TestArchitectureConversions:
    """Tests for architecture conversion functions."""

    def test_architecture_to_linux_runtime_x86_64(self):
        """Test x86_64 to linux-x64 conversion."""
        result = _architecture_to_linux_runtime(X86_64)
        assert result == ARCH_LINUX_AMD64

    def test_architecture_to_linux_runtime_arm64(self):
        """Test arm64 to linux-arm64 conversion."""
        result = _architecture_to_linux_runtime(ARM64)
        assert result == ARCH_LINUX_ARM64

    def test_architecture_to_linux_runtime_invalid(self):
        """Test raises for invalid architecture."""
        with pytest.raises(ValueError, match="Unknown architecture"):
            _architecture_to_linux_runtime("invalid")

    def test_architecture_to_docker_platform_x86_64(self):
        """Test x86_64 to linux/amd64 conversion."""
        result = _architecture_to_docker_platform(X86_64)
        assert result == "linux/amd64"

    def test_architecture_to_docker_platform_arm64(self):
        """Test arm64 to linux/arm64 conversion."""
        result = _architecture_to_docker_platform(ARM64)
        assert result == "linux/arm64"

    def test_architecture_to_docker_platform_invalid(self):
        """Test raises for invalid architecture."""
        with pytest.raises(ValueError, match="Unknown architecture"):
            _architecture_to_docker_platform("invalid")


class TestGetVsdbgCachePath:
    """Tests for get_vsdbg_cache_path function."""

    def test_returns_correct_path_x86_64(self):
        """Test returns correct path for x86_64."""
        with patch("samcli.lib.utils.debugger._get_debugger_cache_dir") as mock_cache:
            mock_cache.return_value = Path("/home/user/.aws-sam/debuggers")
            result = get_vsdbg_cache_path(X86_64)

        expected = Path("/home/user/.aws-sam/debuggers/vsdbg/x86_64")
        assert result == expected

    def test_returns_correct_path_arm64(self):
        """Test returns correct path for arm64."""
        with patch("samcli.lib.utils.debugger._get_debugger_cache_dir") as mock_cache:
            mock_cache.return_value = Path("/home/user/.aws-sam/debuggers")
            result = get_vsdbg_cache_path(ARM64)

        expected = Path("/home/user/.aws-sam/debuggers/vsdbg/arm64")
        assert result == expected


class TestIsVsdbgCached:
    """Tests for is_vsdbg_cached function."""

    def test_returns_true_when_cached(self, tmp_path):
        """Test returns True when vsdbg is cached."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64
        vsdbg_path.mkdir(parents=True)
        (vsdbg_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            result = is_vsdbg_cached(X86_64)

        assert result is True

    def test_returns_false_when_not_cached(self, tmp_path):
        """Test returns False when vsdbg is not cached."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            result = is_vsdbg_cached(X86_64)

        assert result is False


class TestDownloadVsdbg:
    """Tests for download_vsdbg function."""

    def test_uses_cached_when_available(self, tmp_path):
        """Test returns cached path when available."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64
        vsdbg_path.mkdir(parents=True)
        (vsdbg_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
                mock_cached.return_value = True
                result = download_vsdbg(X86_64)

        assert result == str(vsdbg_path)

    def test_downloads_when_not_cached(self, tmp_path):
        """Test downloads when not cached."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
                mock_cached.return_value = False
                with patch("subprocess.run") as mock_run:
                    # Create the vsdbg file to simulate download
                    vsdbg_path.mkdir(parents=True)
                    (vsdbg_path / "vsdbg").write_bytes(b"fake binary")
                    mock_run.return_value = MagicMock(returncode=0, stderr="")

                    result = download_vsdbg(X86_64)

        assert result == str(vsdbg_path)

    def test_force_redownload(self, tmp_path):
        """Test force re-download even when cached."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64
        vsdbg_path.mkdir(parents=True)
        (vsdbg_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                result = download_vsdbg(X86_64, force=True)

        assert result == str(vsdbg_path)

    def test_raises_on_download_failure(self, tmp_path):
        """Test raises DebuggerDownloadError on failure."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
                mock_cached.return_value = False
                with patch("subprocess.run") as mock_run:
                    vsdbg_path.mkdir(parents=True)
                    mock_run.return_value = MagicMock(returncode=1, stderr="Error downloading")

                    with pytest.raises(DebuggerDownloadError, match="Failed to download"):
                        download_vsdbg(X86_64)

    def test_raises_on_docker_not_found(self, tmp_path):
        """Test raises DebuggerDownloadError when Docker not found."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
                mock_cached.return_value = False
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = FileNotFoundError("docker not found")

                    with pytest.raises(DebuggerDownloadError, match="Docker is required"):
                        download_vsdbg(X86_64)

    def test_raises_on_timeout(self, tmp_path):
        """Test raises DebuggerDownloadError on timeout."""
        vsdbg_path = tmp_path / "vsdbg" / X86_64

        with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
            mock_path.return_value = vsdbg_path
            with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
                mock_cached.return_value = False
                with patch("subprocess.run") as mock_run:
                    mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=300)

                    with pytest.raises(DebuggerDownloadError, match="timed out"):
                        download_vsdbg(X86_64)


class TestValidateDebuggerArchitecture:
    """Tests for validate_debugger_architecture function."""

    def test_returns_original_path_when_matching(self, tmp_path):
        """Test returns original path when architectures match."""
        debugger_path = tmp_path / "debugger"
        debugger_path.mkdir()
        (debugger_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.detect_binary_architecture") as mock_detect:
            mock_detect.return_value = X86_64
            result = validate_debugger_architecture(str(debugger_path), X86_64)

        assert result == str(debugger_path)

    def test_returns_original_path_when_no_vsdbg(self, tmp_path):
        """Test returns original path when vsdbg binary not found."""
        debugger_path = tmp_path / "debugger"
        debugger_path.mkdir()  # No vsdbg file

        result = validate_debugger_architecture(str(debugger_path), X86_64)
        assert result == str(debugger_path)

    def test_auto_downloads_on_mismatch(self, tmp_path):
        """Test auto-downloads when architecture mismatch detected."""
        debugger_path = tmp_path / "debugger"
        debugger_path.mkdir()
        (debugger_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.detect_binary_architecture") as mock_detect:
            mock_detect.return_value = ARM64  # Mismatch!
            with patch("samcli.lib.utils.debugger.download_vsdbg") as mock_download:
                mock_download.return_value = "/path/to/x86_64/vsdbg"
                result = validate_debugger_architecture(str(debugger_path), X86_64)

        assert result == "/path/to/x86_64/vsdbg"
        mock_download.assert_called_once_with(X86_64)

    def test_raises_when_auto_download_disabled(self, tmp_path):
        """Test raises exception when auto_download is False."""
        debugger_path = tmp_path / "debugger"
        debugger_path.mkdir()
        (debugger_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.detect_binary_architecture") as mock_detect:
            mock_detect.return_value = ARM64  # Mismatch!

            with pytest.raises(DebuggerArchitectureMismatch) as exc_info:
                validate_debugger_architecture(
                    str(debugger_path), X86_64, auto_download=False
                )

        assert exc_info.value.debugger_arch == ARM64
        assert exc_info.value.container_arch == X86_64

    def test_raises_when_download_fails(self, tmp_path):
        """Test raises exception when download fails."""
        debugger_path = tmp_path / "debugger"
        debugger_path.mkdir()
        (debugger_path / "vsdbg").write_bytes(b"fake binary")

        with patch("samcli.lib.utils.debugger.detect_binary_architecture") as mock_detect:
            mock_detect.return_value = ARM64  # Mismatch!
            with patch("samcli.lib.utils.debugger.download_vsdbg") as mock_download:
                mock_download.side_effect = DebuggerDownloadError("Download failed")

                with pytest.raises(DebuggerArchitectureMismatch):
                    validate_debugger_architecture(str(debugger_path), X86_64)


class TestGetOrDownloadDebugger:
    """Tests for get_or_download_debugger function."""

    def test_validates_user_path(self, tmp_path):
        """Test validates user-provided path."""
        user_path = str(tmp_path / "user-debugger")

        with patch("samcli.lib.utils.debugger.validate_debugger_architecture") as mock_validate:
            mock_validate.return_value = user_path
            result = get_or_download_debugger(DEBUGGER_VSDBG, X86_64, user_path)

        assert result == user_path
        mock_validate.assert_called_once_with(user_path, X86_64, auto_download=True)

    def test_uses_cached_when_no_user_path(self, tmp_path):
        """Test uses cached debugger when no user path provided."""
        cache_path = tmp_path / "cache"

        with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
            mock_cached.return_value = True
            with patch("samcli.lib.utils.debugger.get_vsdbg_cache_path") as mock_path:
                mock_path.return_value = cache_path
                result = get_or_download_debugger(DEBUGGER_VSDBG, X86_64)

        assert result == str(cache_path)

    def test_downloads_when_not_cached(self):
        """Test downloads debugger when not cached."""
        with patch("samcli.lib.utils.debugger.is_vsdbg_cached") as mock_cached:
            mock_cached.return_value = False
            with patch("samcli.lib.utils.debugger.download_vsdbg") as mock_download:
                mock_download.return_value = "/downloaded/path"
                result = get_or_download_debugger(DEBUGGER_VSDBG, X86_64)

        assert result == "/downloaded/path"

    def test_raises_for_unsupported_debugger(self):
        """Test raises ValueError for unsupported debugger type."""
        with pytest.raises(ValueError, match="Unsupported debugger type"):
            get_or_download_debugger("unsupported", X86_64)


class TestClearDebuggerCache:
    """Tests for clear_debugger_cache function."""

    def test_clears_all_cache(self, tmp_path):
        """Test clears all debugger cache."""
        cache_dir = tmp_path / "debuggers"
        cache_dir.mkdir()
        (cache_dir / "vsdbg" / X86_64).mkdir(parents=True)
        (cache_dir / "vsdbg" / ARM64).mkdir(parents=True)

        with patch("samcli.lib.utils.debugger._get_debugger_cache_dir") as mock_cache:
            mock_cache.return_value = cache_dir
            clear_debugger_cache()

        assert not cache_dir.exists()

    def test_clears_specific_debugger(self, tmp_path):
        """Test clears specific debugger cache."""
        cache_dir = tmp_path / "debuggers"
        cache_dir.mkdir()
        vsdbg_dir = cache_dir / "vsdbg"
        vsdbg_dir.mkdir()
        (vsdbg_dir / X86_64).mkdir()
        (vsdbg_dir / ARM64).mkdir()

        with patch("samcli.lib.utils.debugger._get_debugger_cache_dir") as mock_cache:
            mock_cache.return_value = cache_dir
            clear_debugger_cache(debugger_type=DEBUGGER_VSDBG)

        assert not vsdbg_dir.exists()
        assert cache_dir.exists()

    def test_clears_specific_architecture(self, tmp_path):
        """Test clears specific architecture cache."""
        cache_dir = tmp_path / "debuggers"
        cache_dir.mkdir()
        vsdbg_dir = cache_dir / "vsdbg"
        vsdbg_dir.mkdir()
        x86_dir = vsdbg_dir / X86_64
        x86_dir.mkdir()
        arm_dir = vsdbg_dir / ARM64
        arm_dir.mkdir()

        with patch("samcli.lib.utils.debugger._get_debugger_cache_dir") as mock_cache:
            mock_cache.return_value = cache_dir
            clear_debugger_cache(debugger_type=DEBUGGER_VSDBG, architecture=X86_64)

        assert not x86_dir.exists()
        assert arm_dir.exists()


class TestDebuggerArchitectureMismatch:
    """Tests for DebuggerArchitectureMismatch exception."""

    def test_exception_message(self):
        """Test exception message contains useful information."""
        exc = DebuggerArchitectureMismatch(ARM64, X86_64, "/path/to/debugger")

        assert ARM64 in str(exc)
        assert X86_64 in str(exc)
        assert "/path/to/debugger" in str(exc)
        assert exc.debugger_arch == ARM64
        assert exc.container_arch == X86_64
        assert exc.debugger_path == "/path/to/debugger"