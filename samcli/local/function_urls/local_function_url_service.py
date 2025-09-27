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
        # Port assignment logic for single vs multi function mode
        if port and function_name:
            # Single function mode with specific port - use it directly (don't require it to be in range)
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((host, port))
                sock.close()
                # Specified port is available, use it
            except OSError:
                # Specified port not available, try to find alternative
                if port_range and "-" in port_range:
                    start_port = int(port_range.split("-")[0])
                    end_port = int(port_range.split("-")[1])
                    port = find_free_port(host, start_port, end_port)
                else:
                    port = find_free_port(host, 3001, 3010)
                LOG.warning(f"Specified port not available, using {port} instead")
        elif port_range and "-" in port_range:
            # Multi-function mode with port range
            start_port = int(port_range.split("-")[0])
            end_port = int(port_range.split("-")[1])
            if port and start_port <= port <= end_port:
                # Specific port within range, try it
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.bind((host, port))
                    sock.close()
                except OSError:
                    port = find_free_port(host, start_port, end_port)
            else:
                # Use range for auto-assignment
                port = find_free_port(host, start_port, end_port)
        elif not port:
            # No port specified, use default range
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

        # Filter functions if specific function requested
        functions_to_start = self.function_urls
        if self.function_name:
            functions_to_start = [fu for fu in self.function_urls if fu.function_name == self.function_name]

        # Validate we have enough ports for all functions
        total_ports_needed = len(functions_to_start)
        total_ports_available = end_port - start_port + 1
        if total_ports_needed > total_ports_available:
            raise RuntimeError(
                f"Not enough ports in range {start_port}-{end_port}. "
                f"Need {total_ports_needed} ports but only {total_ports_available} available. "
                f"Use a wider --port-range or start fewer functions."
            )

        # Track used ports to avoid conflicts
        used_ports = set()
        
        # Create a handler for each function URL
        for i, function_url in enumerate(functions_to_start):
            # Find available port
            if self.port and (len(functions_to_start) == 1 or self.function_name):
                # Use specified port for single function or when function name is specified
                port = self.port
            else:
                # Sequential port allocation starting from start_port
                port = None
                for attempt_port in range(start_port, end_port + 1):
                    if attempt_port not in used_ports:
                        try:
                            # Test if this specific port is available
                            import socket
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.bind((self.host, attempt_port))
                            sock.close()
                            port = attempt_port
                            break
                        except OSError:
                            # Port not available, try next
                            continue
                
                if port is None:
                    raise RuntimeError(
                        f"Unable to find free port for function {function_url.function_name} "
                        f"in range {start_port}-{end_port}. Ports in use: {sorted(used_ports)}"
                    )
            
            # Reserve the port
            used_ports.add(port)

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
