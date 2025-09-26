"""
Shared base class for start-api and start-function-urls integration tests
"""

import os
import shutil
import uuid
import logging
from pathlib import Path
from subprocess import Popen, PIPE
from typing import Optional, Dict, List
from unittest import TestCase, skipIf

import docker
from docker.errors import APIError
from psutil import NoSuchProcess

from tests.integration.local.common_utils import InvalidAddressException, random_port, wait_for_local_process
from tests.testing_utils import (
    SKIP_DOCKER_MESSAGE,
    SKIP_DOCKER_TESTS,
    run_command,
    kill_process,
    get_sam_command,
)

LOG = logging.getLogger(__name__)


@skipIf(SKIP_DOCKER_TESTS, SKIP_DOCKER_MESSAGE)
class SharedStartServiceBase(TestCase):
    """
    Shared base class for start-api and start-function-urls integration tests
    """

    template: Optional[str] = None
    container_mode: Optional[str] = None
    parameter_overrides: Optional[Dict[str, str]] = None
    binary_data_file: Optional[str] = None
    integration_dir = str(Path(__file__).resolve().parents[2])
    invoke_image: Optional[List] = None
    layer_cache_base_dir: Optional[str] = None
    config_file: Optional[str] = None

    build_before_invoke = False
    build_overrides: Optional[Dict[str, str]] = None

    do_collect_cmd_init_output: bool = False

    command_list = None
    project_directory = None

    @classmethod
    def common_setup(cls):
        """Common setup for both start-api and start-function-urls"""
        # This is the directory for tests/integration which will be used to find the testdata
        # files for integ tests
        cls.integration_dir = str(Path(__file__).resolve().parents[2])

        if hasattr(cls, "template_path"):
            cls.template = cls.integration_dir + cls.template_path

        if cls.binary_data_file:
            cls.binary_data_file = os.path.join(cls.integration_dir, cls.binary_data_file)

        if cls.build_before_invoke:
            cls.build()

        # Initialize Docker client and clean up containers
        cls.docker_client = docker.from_env()
        for container in cls.docker_client.api.containers():
            try:
                cls.docker_client.api.remove_container(container, force=True)
            except APIError as ex:
                LOG.error("Failed to remove container %s", container, exc_info=ex)

    @classmethod
    def build(cls):
        """Build the SAM application"""
        command = get_sam_command()
        command_list = [command, "build"]
        if cls.build_overrides:
            overrides_arg = " ".join(
                ["ParameterKey={},ParameterValue={}".format(key, value) for key, value in cls.build_overrides.items()]
            )
            command_list += ["--parameter-overrides", overrides_arg]
        working_dir = str(Path(cls.template).resolve().parents[0])
        run_command(command_list, cwd=working_dir)

    @classmethod
    def _make_parameter_override_arg(cls, overrides):
        """Make parameter override argument string"""
        return " ".join(["ParameterKey={},ParameterValue={}".format(key, value) for key, value in overrides.items()])

    @classmethod
    def common_teardown(cls, process, stop_reading_thread=False):
        """Common teardown for both start-api and start-function-urls"""
        # Stop reading thread if applicable
        if hasattr(cls, "stop_reading_thread"):
            cls.stop_reading_thread = True

        # Stop the reading threads first
        if hasattr(cls, "read_threading"):
            cls.read_threading.join(timeout=1)
        if hasattr(cls, "read_threading2"):
            cls.read_threading2.join(timeout=1)

        try:
            if process:
                # First try to terminate gracefully
                process.terminate()
                try:
                    process.wait(timeout=2)
                except:
                    # If that doesn't work, force kill
                    kill_process(process)
                finally:
                    # Close the pipes to prevent resource warnings
                    if process.stdout:
                        process.stdout.close()
                    if process.stderr:
                        process.stderr.close()
        except (NoSuchProcess, AttributeError) as e:
            LOG.info(f"Process cleanup: {e}")

    @staticmethod
    def get_binary_data(filename):
        """Get binary data from file"""
        if not filename:
            return None

        with open(filename, "rb") as fp:
            return fp.read()


class WritableSharedStartServiceBase(SharedStartServiceBase):
    """
    Shared base class for start-api and start-function-urls integration tests with writable templates
    """

    temp_path: Optional[str] = None
    template_path: Optional[str] = None
    code_path: Optional[str] = None
    docker_file_path: Optional[str] = None

    template_content: Optional[str] = None
    code_content: Optional[str] = None
    docker_file_content: Optional[str] = None

    @classmethod
    def writable_setup(cls):
        """Set up test class with writable templates"""
        # Set up the integration directory first
        cls.integration_dir = str(Path(__file__).resolve().parents[2])

        # Create temporary directory for test files
        cls.temp_path = str(uuid.uuid4()).replace("-", "")[:10]
        working_dir = str(Path(cls.integration_dir).resolve().joinpath(cls.temp_path))
        if Path(working_dir).resolve().exists():
            shutil.rmtree(working_dir, ignore_errors=True)
        os.mkdir(working_dir)
        os.mkdir(Path(cls.integration_dir).resolve().joinpath(cls.temp_path).joinpath("dir"))

        # Set up file paths
        cls.template_path = f"/{cls.temp_path}/template.yaml"
        cls.code_path = f"/{cls.temp_path}/main.py"
        cls.code_path2 = f"/{cls.temp_path}/dir/main2.py"
        cls.docker_file_path = f"/{cls.temp_path}/Dockerfile"
        cls.docker_file_path2 = f"/{cls.temp_path}/Dockerfile2"

        # Write file contents
        if cls.template_content:
            cls._write_file_content(cls.template_path, cls.template_content)

        if cls.code_content:
            cls._write_file_content(cls.code_path, cls.code_content)

        if cls.docker_file_content:
            cls._write_file_content(cls.docker_file_path, cls.docker_file_content)

    @classmethod
    def _write_file_content(cls, path, content):
        """Write content to file"""
        with open(cls.integration_dir + path, "w") as f:
            f.write(content)

    @classmethod
    def writable_teardown(cls):
        """Tear down test class with writable templates"""
        working_dir = str(Path(cls.integration_dir).resolve().joinpath(cls.temp_path))
        if Path(working_dir).resolve().exists():
            shutil.rmtree(working_dir, ignore_errors=True)
