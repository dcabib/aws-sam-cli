"""Function URL Local Service"""

import logging
from typing import Optional

from samcli.commands.local.lib.local_lambda import LocalLambdaRunner
from samcli.lib.utils.stream_writer import StreamWriter
from samcli.local.docker.utils import find_free_port
from samcli.local.services.base_local_service import BaseLocalService

LOG = logging.getLogger(__name__)


class LocalFunctionUrlsService(BaseLocalService):
    """
    Local service for Function URLs that creates individual Flask apps for each function
    """

    def __init__(
        self,
        function_urls,
        lambda_runner: LocalLambdaRunner,
        port: Optional[int] = None,
        host: str = "127.0.0.1",
        port_range: str = "3001-3010",
        function_name: Optional[str] = None,
        disable_authorizer: bool = False,
        stderr: Optional[StreamWriter] = None,
    ):
        """
        Initialize the Function URL service

        Parameters
        ----------
        function_urls : list
            List of FunctionUrl objects
        lambda_runner : LocalLambdaRunner
            Lambda runner for function invocation
        port : int, optional
            Specific port for single function mode
        host : str
            Host to bind to
        port_range : str
            Port range for auto-assignment
        function_name : str, optional
            Specific function to start
        disable_authorizer : bool
            Whether to disable authorization checks
        stderr : StreamWriter, optional
            Stream for error output
        """
        # Always try to find a free port in the range, even if port is specified
        if port_range and "-" in port_range:
            start_port = int(port_range.split("-")[0])
            end_port = int(port_range.split("-")[1])
            # If a specific port is requested, try it first
            if port and start_port <= port <= end_port:
                try:
                    # Test if the requested port is available
                    import socket

                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.bind((host, port))
                    sock.close()
                    # Port is available, use it
                except OSError:
                    # Port is not available, find a free one in range
                    port = find_free_port(host, start_port, end_port)
            else:
                # Find any free port in range
                port = find_free_port(host, start_port, end_port)
        elif not port:
            # Fallback to default range if no port_range specified
            port = find_free_port(host, 3001, 3010)

        super().__init__(is_debugging=lambda_runner.is_debugging(), port=port, host=host, ssl_context=None)

        self.function_urls = function_urls
        self.lambda_runner = lambda_runner
        self.port_range = port_range
        self.function_name = function_name
        self.disable_authorizer = disable_authorizer
        self.stderr = stderr
        self.services: list = []

    def create(self):
        """
        Creates Flask Applications for Function URLs.
        For Function URLs, each function gets its own Flask app on separate port.
        """
        from samcli.commands.local.lib.function_url_handler import FunctionUrlHandler

        # Parse port range
        if "-" in self.port_range:
            start_port, end_port = map(int, self.port_range.split("-"))
        else:
            start_port = int(self.port_range)
            end_port = start_port + 10

        current_port = start_port

        # Filter functions if specific function requested
        functions_to_start = self.function_urls
        if self.function_name:
            functions_to_start = [fu for fu in self.function_urls if fu.function_name == self.function_name]

        # Create a handler for each function URL
        for function_url in functions_to_start:
            # Find available port
            if self.port and (len(functions_to_start) == 1 or self.function_name):
                # Use specified port for single function or when function name is specified
                port = self.port
            else:
                # Find next available port in range
                port = find_free_port(self.host, current_port, end_port)
                current_port = port + 1

            # Create handler for this function
            handler = FunctionUrlHandler(
                function_name=function_url.function_name,
                function_config=function_url.config,
                local_lambda_runner=self.lambda_runner,
                port=port,
                host=self.host,
                disable_authorizer=self.disable_authorizer,
                stderr=self.stderr,
                is_debugging=self.lambda_runner.is_debugging(),
            )

            # This will be a separate Flask app, but we need to properly use BaseLocalService
            handler.create()
            self.services.append(handler)

    def run(self):
        """
        Start all Function URL services
        """
        if not self.services:
            raise RuntimeError("No Function URL services created. Call create() first.")

        # For single function, run directly
        if len(self.services) == 1:
            self.services[0].run()
        else:
            # For multiple functions, we need to start them in separate threads
            import threading

            threads = []
            for service in self.services:
                thread = threading.Thread(target=service.run, daemon=True)
                thread.start()
                threads.append(thread)

            # Wait for all threads
            try:
                for thread in threads:
                    thread.join()
            except KeyboardInterrupt:
                LOG.info("Received keyboard interrupt")
