"""
Connects the CLI with Local Function URL service.
"""

import logging

from samcli.commands.local.lib.exceptions import NoFunctionUrlsDefined
from samcli.lib.providers.function_url_provider import FunctionUrlProvider
from samcli.local.function_urls.local_function_url_service import LocalFunctionUrlsService

LOG = logging.getLogger(__name__)


class LocalFunctionUrlService:
    """
    Implementation of Local Function URL service that is capable of serving Functions with Function URLs
    defined in a configuration file that invoke a Lambda function.
    """

    def __init__(
        self,
        lambda_invoke_context,
        port=None,
        host="127.0.0.1",
        port_range="3001-3010",
        function_name=None,
        disable_authorizer=False,
    ):
        """
        Initialize the local Function URL service.

        :param samcli.commands.local.cli_common.invoke_context.InvokeContext lambda_invoke_context: Context object
            that can help with Lambda invocation
        :param int port: Port to listen on for single function mode
        :param string host: Local hostname or IP address to bind to
        :param string port_range: Port range for auto-assignment
        :param string function_name: Optional, specific function to start
        :param bool disable_authorizer: Optional, flag for disabling authorization checks
        """

        self.port = port
        self.host = host
        self.port_range = port_range
        self.function_name = function_name
        self.disable_authorizer = disable_authorizer

        self.cwd = lambda_invoke_context.get_cwd()
        self.function_url_provider = FunctionUrlProvider(lambda_invoke_context.stacks, cwd=self.cwd)
        self.lambda_runner = lambda_invoke_context.local_lambda_runner
        self.stderr_stream = lambda_invoke_context.stderr

    def start(self):
        """
        Creates and starts the local Function URL service. This method will block until the service is stopped
        manually using an interrupt. After the service is started, callers can make HTTP requests to the endpoints
        to invoke the Lambda function and receive a response.

        NOTE: This is a blocking call that will not return until the thread is interrupted with SIGINT/SIGTERM
        """

        if not self.function_url_provider.function_urls:
            raise NoFunctionUrlsDefined("No Function URLs available in template")

        # Smart single-function detection and validation (addresses valerena's issue #69)
        available_functions = [fu.function_name for fu in self.function_url_provider.function_urls]

        if self.function_name:
            # Validate the specified function exists
            if self.function_name not in available_functions:
                functions_list = ", ".join(available_functions)
                raise NoFunctionUrlsDefined(
                    f"Function '{self.function_name}' not found. Available functions: {functions_list}"
                )
        elif len(available_functions) == 1 and self.port:
            # Auto-select single function when port is specified
            self.function_name = available_functions[0]
            LOG.info(f"Auto-selecting function '{self.function_name}' (only function with Function URL configuration)")

        # We care about passing only stderr to the Service and not stdout because stdout from Docker container
        # contains the response to the function which is sent out as HTTP response. Only stderr needs to be printed
        # to the console or a log file. stderr from Docker container contains runtime logs and output of print
        # statements from the Lambda function
        service = LocalFunctionUrlsService(
            function_urls=self.function_url_provider.function_urls,
            lambda_runner=self.lambda_runner,
            port=self.port,
            host=self.host,
            port_range=self.port_range,
            function_name=self.function_name,
            disable_authorizer=self.disable_authorizer,
            stderr=self.stderr_stream,
        )

        service.create()

        # Filter function URLs for printing if specific function requested
        functions_to_print = self.function_url_provider.function_urls
        if self.function_name:
            functions_to_print = [fu for fu in self.function_url_provider.function_urls if fu.function_name == self.function_name]

        # Print out the list of function URLs that will be mounted with correct port info
        # For single function with specific port, show that port; otherwise use range logic
        if self.function_name and self.port and len(functions_to_print) == 1:
            # Single function mode with specific port
            function_url = functions_to_print[0]
            output = "Mounting {} at http://{}:{}/".format(function_url.function_name, self.host, self.port)
            LOG.info(output)
        else:
            # Multiple functions or auto-port assignment
            self._print_function_urls(functions_to_print, self.host, self.port, self.port_range)
        LOG.info(
            "You can now browse to the above endpoints to invoke your functions. "
            "You do not need to restart/reload SAM CLI while working on your functions, "
            "changes will be reflected instantly/automatically. If you used sam build before "
            "running local commands, you will need to re-run sam build for the changes "
            "to be picked up. You only need to restart SAM CLI if you update your AWS SAM template"
        )

        service.run()

    @staticmethod
    def _print_function_urls(function_urls, host, single_port, port_range):
        """
        Helper method to print the Function URLs that will be mounted. This method is purely for printing purposes.
        Follows the same format as LocalApiService._print_routes for consistency.

        :param list function_urls: List of function URL configurations
        :param string host: Host name where the service is running
        :param int single_port: Single port if specified for single function
        :param string port_range: Port range for auto-assignment
        :returns list(string): List of lines that were printed to the console. Helps with testing
        """

        print_lines = []

        # Determine starting port
        if single_port and len(function_urls) == 1:
            start_port = single_port
        elif isinstance(port_range, str) and "-" in port_range:
            start_port, _ = map(int, port_range.split("-"))
        else:
            start_port = 3001

        current_port = start_port

        for function_url in function_urls:
            function_name = function_url.function_name

            # Format matches LocalApiService._print_routes format for consistency
            output = "Mounting {} at http://{}:{}/".format(function_name, host, current_port)
            print_lines.append(output)
            LOG.info(output)

            current_port += 1

        return print_lines
