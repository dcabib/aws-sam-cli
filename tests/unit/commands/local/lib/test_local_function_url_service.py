"""
Unit tests for LocalFunctionUrlService
"""

import unittest
from unittest.mock import Mock, patch

from samcli.commands.local.lib.local_function_url_service import LocalFunctionUrlService
from samcli.commands.local.lib.exceptions import NoFunctionUrlsDefined


class TestLocalFunctionUrlService(unittest.TestCase):
    """Test the LocalFunctionUrlService class following LocalApiService patterns"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock InvokeContext
        self.invoke_context = Mock()
        self.invoke_context.get_cwd.return_value = "/test/dir"
        self.invoke_context.local_lambda_runner = Mock()
        self.invoke_context.stderr = Mock()
        self.invoke_context.stacks = []

        # Test parameters
        self.host = "127.0.0.1"
        self.port_range = "3001-3010"

    @patch("samcli.lib.providers.function_url_provider.FunctionUrlProvider")
    def test_init_basic(self, mock_provider_class):
        """Test basic initialization"""
        # Setup
        mock_provider = Mock()
        mock_provider.function_urls = []
        mock_provider_class.return_value = mock_provider

        # Execute
        service = LocalFunctionUrlService(
            lambda_invoke_context=self.invoke_context, host=self.host, port_range=self.port_range
        )

        # Verify initialization
        self.assertEqual(service.host, self.host)
        self.assertEqual(service.port_range, self.port_range)
        self.assertEqual(service.function_name, None)
        self.assertFalse(service.disable_authorizer)

    def test_start_with_function_urls(self):
        """Test starting service with Function URLs"""
        with patch(
            "samcli.commands.local.lib.local_function_url_service.LocalFunctionUrlsService"
        ) as mock_service_class:

            # Setup mock provider
            mock_function_url = Mock()
            mock_function_url.function_name = "TestFunction"

            mock_provider = Mock()
            mock_provider.function_urls = [mock_function_url]

            # Setup mock service that doesn't actually start Flask
            mock_service = Mock()
            mock_service.create = Mock()
            mock_service.run = Mock()
            mock_service_class.return_value = mock_service

            # Execute - create service then override provider
            service = LocalFunctionUrlService(
                lambda_invoke_context=self.invoke_context, host=self.host, port_range=self.port_range
            )

            # Override the provider that was created during init
            service.function_url_provider = mock_provider

            service.start()

            # Verify service creation and start
            mock_service_class.assert_called_once()
            mock_service.create.assert_called_once()
            mock_service.run.assert_called_once()

    @patch("samcli.lib.providers.function_url_provider.FunctionUrlProvider")
    def test_start_no_function_urls(self, mock_provider_class):
        """Test starting service when no Function URLs exist"""
        # Setup
        mock_provider = Mock()
        mock_provider.function_urls = []
        mock_provider_class.return_value = mock_provider

        service = LocalFunctionUrlService(
            lambda_invoke_context=self.invoke_context, host=self.host, port_range=self.port_range
        )

        # Execute and verify
        with self.assertRaises(NoFunctionUrlsDefined) as context:
            service.start()

        self.assertIn("No Function URLs available in template", str(context.exception))

    def test_start_with_specific_function(self):
        """Test starting service with specific function name"""
        with patch(
            "samcli.commands.local.lib.local_function_url_service.LocalFunctionUrlsService"
        ) as mock_service_class:

            # Setup mock provider
            mock_function_url1 = Mock()
            mock_function_url1.function_name = "Function1"
            mock_function_url2 = Mock()
            mock_function_url2.function_name = "Function2"

            mock_provider = Mock()
            mock_provider.function_urls = [mock_function_url1, mock_function_url2]

            # Setup mock service that doesn't actually start Flask
            mock_service = Mock()
            mock_service.create = Mock()
            mock_service.run = Mock()
            mock_service_class.return_value = mock_service

            # Execute
            service = LocalFunctionUrlService(
                lambda_invoke_context=self.invoke_context,
                host=self.host,
                port_range=self.port_range,
                function_name="Function1",
            )

            # Override the provider that was created during init
            service.function_url_provider = mock_provider

            service.start()

            # Verify correct function is selected
            call_args = mock_service_class.call_args[1]
            self.assertEqual(call_args["function_name"], "Function1")

    @patch("samcli.lib.providers.function_url_provider.FunctionUrlProvider")
    def test_start_with_invalid_function(self, mock_provider_class):
        """Test starting service with invalid function name"""
        # Setup mock provider
        mock_function_url = Mock()
        mock_function_url.function_name = "ExistingFunction"

        mock_provider = Mock()
        mock_provider.function_urls = [mock_function_url]
        mock_provider_class.return_value = mock_provider

        service = LocalFunctionUrlService(
            lambda_invoke_context=self.invoke_context,
            host=self.host,
            port_range=self.port_range,
            function_name="NonExistentFunction",
        )

        # Override the provider instance that was created during init
        service.function_url_provider = mock_provider

        # Execute and verify
        with self.assertRaises(NoFunctionUrlsDefined) as context:
            service.start()

        self.assertIn("NonExistentFunction", str(context.exception))
        self.assertIn("Available functions: ExistingFunction", str(context.exception))

    @patch("samcli.lib.providers.function_url_provider.FunctionUrlProvider")
    def test_print_function_urls_single_port(self, mock_provider_class):
        """Test printing Function URLs with single port"""
        # Setup mock function URL
        mock_function_url = Mock()
        mock_function_url.function_name = "TestFunction"
        function_urls = [mock_function_url]

        # Execute
        lines = LocalFunctionUrlService._print_function_urls(function_urls, "127.0.0.1", 3000, "3001-3010")

        # Verify
        self.assertEqual(len(lines), 1)
        self.assertIn("TestFunction", lines[0])
        self.assertIn("http://127.0.0.1:3000/", lines[0])

    @patch("samcli.lib.providers.function_url_provider.FunctionUrlProvider")
    def test_print_function_urls_port_range(self, mock_provider_class):
        """Test printing Function URLs with port range"""
        # Setup mock function URLs
        mock_function_url1 = Mock()
        mock_function_url1.function_name = "Function1"
        mock_function_url2 = Mock()
        mock_function_url2.function_name = "Function2"
        function_urls = [mock_function_url1, mock_function_url2]

        # Execute
        lines = LocalFunctionUrlService._print_function_urls(function_urls, "127.0.0.1", None, "3001-3010")

        # Verify
        self.assertEqual(len(lines), 2)
        self.assertIn("Function1", lines[0])
        self.assertIn("http://127.0.0.1:3001/", lines[0])
        self.assertIn("Function2", lines[1])
        self.assertIn("http://127.0.0.1:3002/", lines[1])


if __name__ == "__main__":
    unittest.main()
