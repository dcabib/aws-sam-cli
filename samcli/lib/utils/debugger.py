"""
Debugger utilities for managing debugger binaries across different architectures.

This module provides functionality to:
- Detect the architecture of debugger binaries
- Download debugger binaries for specific architectures
- Manage debugger cache to avoid repeated downloads
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from samcli.cli.global_config import GlobalConfig
from samcli.lib.utils.architecture import ARM64, X86_64

LOG = logging.getLogger(__name__)

# Supported debuggers
DEBUGGER_VSDBG = "vsdbg"
DEBUGGER_DELVE = "delve"

# Architecture mapping for debugger downloads
ARCH_LINUX_AMD64 = "linux-x64"
ARCH_LINUX_ARM64 = "linux-arm64"

# vsdbg download script URL
VSDBG_INSTALL_SCRIPT_URL = "https://aka.ms/getvsdbgsh"

# Docker images for downloading debuggers
# Using SDK image because it has curl pre-installed
DOTNET_SDK_IMAGE = "mcr.microsoft.com/dotnet/sdk:6.0"


class DebuggerArchitectureMismatch(Exception):
    """Raised when debugger architecture doesn't match the container architecture."""

    def __init__(self, debugger_arch: str, container_arch: str, debugger_path: str):
        self.debugger_arch = debugger_arch
        self.container_arch = container_arch
        self.debugger_path = debugger_path
        super().__init__(
            f"Debugger at '{debugger_path}' is built for {debugger_arch} but container runs {container_arch}. "
            f"Debugging will not work. Consider using '--debugger-architecture {container_arch}' "
            f"or let SAM CLI auto-download the correct debugger."
        )


class DebuggerDownloadError(Exception):
    """Raised when debugger download fails."""

    pass


def _get_debugger_cache_dir() -> Path:
    """
    Get the directory for caching debugger binaries.

    Returns
    -------
    Path
        Path to the debugger cache directory
    """
    global_config = GlobalConfig()
    config_dir = Path(global_config.config_dir)
    debugger_dir = config_dir / "debuggers"
    debugger_dir.mkdir(parents=True, exist_ok=True)
    return debugger_dir


def detect_binary_architecture(binary_path: str) -> Optional[str]:
    """
    Detect the architecture of a binary file using the 'file' command.

    Parameters
    ----------
    binary_path : str
        Path to the binary file

    Returns
    -------
    Optional[str]
        The architecture (X86_64 or ARM64), or None if detection fails
    """
    if not os.path.exists(binary_path):
        LOG.warning("Binary path does not exist: %s", binary_path)
        return None

    try:
        result = subprocess.run(
            ["file", binary_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = result.stdout.lower()

        if "x86-64" in output or "x86_64" in output or "amd64" in output:
            return X86_64
        elif "aarch64" in output or "arm64" in output or "arm aarch64" in output:
            return ARM64

        LOG.debug("Could not determine architecture from file output: %s", output)
        return None
    except subprocess.TimeoutExpired:
        LOG.warning("Timeout while detecting binary architecture for: %s", binary_path)
        return None
    except FileNotFoundError:
        LOG.warning("'file' command not found, cannot detect binary architecture")
        return None
    except Exception as e:
        LOG.warning("Error detecting binary architecture: %s", str(e))
        return None


def _architecture_to_linux_runtime(architecture: str) -> str:
    """
    Convert SAM CLI architecture to Linux runtime identifier.

    Parameters
    ----------
    architecture : str
        SAM CLI architecture (x86_64 or arm64)

    Returns
    -------
    str
        Linux runtime identifier (linux-x64 or linux-arm64)
    """
    if architecture == X86_64:
        return ARCH_LINUX_AMD64
    elif architecture == ARM64:
        return ARCH_LINUX_ARM64
    else:
        raise ValueError(f"Unknown architecture: {architecture}")


def _architecture_to_docker_platform(architecture: str) -> str:
    """
    Convert SAM CLI architecture to Docker platform string.

    Parameters
    ----------
    architecture : str
        SAM CLI architecture (x86_64 or arm64)

    Returns
    -------
    str
        Docker platform string (linux/amd64 or linux/arm64)
    """
    if architecture == X86_64:
        return "linux/amd64"
    elif architecture == ARM64:
        return "linux/arm64"
    else:
        raise ValueError(f"Unknown architecture: {architecture}")


def get_vsdbg_cache_path(architecture: str) -> Path:
    """
    Get the cache path for vsdbg for a specific architecture.

    Parameters
    ----------
    architecture : str
        Target architecture (x86_64 or arm64)

    Returns
    -------
    Path
        Path to the vsdbg cache directory for this architecture
    """
    cache_dir = _get_debugger_cache_dir()
    return cache_dir / DEBUGGER_VSDBG / architecture


def is_vsdbg_cached(architecture: str) -> bool:
    """
    Check if vsdbg is already cached for the specified architecture.

    Parameters
    ----------
    architecture : str
        Target architecture (x86_64 or arm64)

    Returns
    -------
    bool
        True if vsdbg is cached and appears valid
    """
    cache_path = get_vsdbg_cache_path(architecture)
    vsdbg_binary = cache_path / "vsdbg"
    return vsdbg_binary.exists()


def download_vsdbg(architecture: str, force: bool = False) -> str:
    """
    Download vsdbg for the specified architecture.

    Uses Docker to download the correct architecture version, which ensures
    the download script detects the correct platform.

    Parameters
    ----------
    architecture : str
        Target architecture (x86_64 or arm64)
    force : bool
        If True, re-download even if cached

    Returns
    -------
    str
        Path to the downloaded vsdbg directory

    Raises
    ------
    DebuggerDownloadError
        If the download fails
    """
    cache_path = get_vsdbg_cache_path(architecture)

    # Check if already cached
    if not force and is_vsdbg_cached(architecture):
        LOG.info("Using cached vsdbg for %s architecture at %s", architecture, cache_path)
        return str(cache_path)

    LOG.info("Downloading vsdbg for %s architecture...", architecture)

    # Create cache directory
    cache_path.mkdir(parents=True, exist_ok=True)

    # Get Docker platform string
    docker_platform = _architecture_to_docker_platform(architecture)
    linux_runtime = _architecture_to_linux_runtime(architecture)

    try:
        # Use Docker to download vsdbg for the correct architecture
        # The --platform flag ensures we get the correct architecture binary
        cmd = [
            "docker",
            "run",
            "--rm",
            "--platform",
            docker_platform,
            "--mount",
            f"type=bind,src={cache_path},dst=/vsdbg",
            DOTNET_SDK_IMAGE,
            "bash",
            "-c",
            f"curl -sSL {VSDBG_INSTALL_SCRIPT_URL} | bash /dev/stdin -v latest -l /vsdbg -r {linux_runtime}",
        ]

        LOG.debug("Running command: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
            check=False,
        )

        if result.returncode != 0:
            LOG.error("Failed to download vsdbg: %s", result.stderr)
            raise DebuggerDownloadError(f"Failed to download vsdbg: {result.stderr}")

        # Verify the download
        vsdbg_binary = cache_path / "vsdbg"
        if not vsdbg_binary.exists():
            raise DebuggerDownloadError(f"vsdbg binary not found after download at {vsdbg_binary}")

        # Verify architecture
        detected_arch = detect_binary_architecture(str(vsdbg_binary))
        if detected_arch and detected_arch != architecture:
            LOG.warning(
                "Downloaded vsdbg architecture (%s) doesn't match requested (%s). "
                "This may indicate a Docker platform emulation issue.",
                detected_arch,
                architecture,
            )

        LOG.info("Successfully downloaded vsdbg for %s to %s", architecture, cache_path)
        return str(cache_path)

    except subprocess.TimeoutExpired:
        raise DebuggerDownloadError("vsdbg download timed out after 5 minutes")
    except FileNotFoundError:
        raise DebuggerDownloadError("Docker is required to download vsdbg but was not found")
    except Exception as e:
        raise DebuggerDownloadError(f"Failed to download vsdbg: {str(e)}")


def validate_debugger_architecture(
    debugger_path: str,
    container_architecture: str,
    auto_download: bool = True,
) -> str:
    """
    Validate that the debugger binary matches the container architecture.

    If auto_download is True and there's a mismatch, attempts to download
    the correct version.

    Parameters
    ----------
    debugger_path : str
        Path to the debugger directory (e.g., ~/.vsdbg)
    container_architecture : str
        Target container architecture (x86_64 or arm64)
    auto_download : bool
        If True, automatically download the correct debugger on mismatch

    Returns
    -------
    str
        Path to use for the debugger (original or newly downloaded)

    Raises
    ------
    DebuggerArchitectureMismatch
        If architectures don't match and auto_download is False
    """
    # Find the vsdbg binary in the debugger path
    vsdbg_binary = Path(debugger_path) / "vsdbg"
    if not vsdbg_binary.exists():
        LOG.debug("vsdbg binary not found at %s, assuming compatible", debugger_path)
        return debugger_path

    # Detect the architecture of the provided debugger
    debugger_arch = detect_binary_architecture(str(vsdbg_binary))

    if debugger_arch is None:
        LOG.warning("Could not detect debugger architecture, proceeding anyway")
        return debugger_path

    if debugger_arch == container_architecture:
        LOG.debug("Debugger architecture (%s) matches container", debugger_arch)
        return debugger_path

    # Architecture mismatch detected
    LOG.warning(
        "Debugger architecture mismatch: debugger is %s but container is %s",
        debugger_arch,
        container_architecture,
    )

    if not auto_download:
        raise DebuggerArchitectureMismatch(debugger_arch, container_architecture, debugger_path)

    # Attempt to download the correct version
    LOG.info("Attempting to download vsdbg for %s architecture...", container_architecture)
    try:
        correct_path = download_vsdbg(container_architecture)
        LOG.info(
            "Using auto-downloaded vsdbg from %s instead of user-provided path %s",
            correct_path,
            debugger_path,
        )
        return correct_path
    except DebuggerDownloadError as e:
        LOG.error("Failed to auto-download debugger: %s", str(e))
        raise DebuggerArchitectureMismatch(debugger_arch, container_architecture, debugger_path) from e


def get_or_download_debugger(
    debugger_type: str,
    architecture: str,
    user_debugger_path: Optional[str] = None,
) -> str:
    """
    Get a debugger path, downloading if necessary.

    If a user-provided path is given, validates it matches the architecture.
    If no path is provided or validation fails, downloads the correct version.

    Parameters
    ----------
    debugger_type : str
        Type of debugger (e.g., DEBUGGER_VSDBG)
    architecture : str
        Target architecture (x86_64 or arm64)
    user_debugger_path : Optional[str]
        Optional user-provided debugger path

    Returns
    -------
    str
        Path to the debugger directory

    Raises
    ------
    ValueError
        If debugger_type is not supported
    DebuggerDownloadError
        If download fails
    """
    if debugger_type != DEBUGGER_VSDBG:
        raise ValueError(f"Unsupported debugger type: {debugger_type}. Supported: {DEBUGGER_VSDBG}")

    # If user provided a path, validate it
    if user_debugger_path:
        return validate_debugger_architecture(
            user_debugger_path,
            architecture,
            auto_download=True,
        )

    # No user path, check cache or download
    if is_vsdbg_cached(architecture):
        cache_path = get_vsdbg_cache_path(architecture)
        LOG.debug("Using cached vsdbg at %s", cache_path)
        return str(cache_path)

    # Download
    return download_vsdbg(architecture)


def clear_debugger_cache(debugger_type: Optional[str] = None, architecture: Optional[str] = None) -> None:
    """
    Clear the debugger cache.

    Parameters
    ----------
    debugger_type : Optional[str]
        If specified, only clear this debugger type. Otherwise, clear all.
    architecture : Optional[str]
        If specified, only clear this architecture. Otherwise, clear all.
    """
    import shutil

    cache_dir = _get_debugger_cache_dir()

    if debugger_type is None and architecture is None:
        # Clear everything
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            LOG.info("Cleared all debugger cache at %s", cache_dir)
        return

    if debugger_type:
        debugger_dir = cache_dir / debugger_type
        if architecture:
            arch_dir = debugger_dir / architecture
            if arch_dir.exists():
                shutil.rmtree(arch_dir)
                LOG.info("Cleared %s debugger cache for %s at %s", debugger_type, architecture, arch_dir)
        elif debugger_dir.exists():
            shutil.rmtree(debugger_dir)
            LOG.info("Cleared all %s debugger cache at %s", debugger_type, debugger_dir)
