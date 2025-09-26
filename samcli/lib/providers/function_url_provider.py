"""Class that provides Functions with Function URLs from a Template"""

import logging
from typing import Iterator, List, Optional

from samcli.lib.providers.provider import Stack
from samcli.lib.providers.sam_function_provider import SamFunctionProvider

LOG = logging.getLogger(__name__)


class FunctionUrl:
    """
    Represents a Function URL configuration
    """

    def __init__(self, function_name: str, config: dict, function_definition: dict):
        """
        Initialize Function URL

        Parameters
        ----------
        function_name : str
            Name of the Lambda function
        config : dict
            Function URL configuration
        function_definition : dict
            Complete function definition from template
        """
        self.function_name = function_name
        self.config = config
        self.function_definition = function_definition


class FunctionUrlProvider:
    def __init__(self, stacks: List[Stack], cwd: Optional[str] = None):
        """
        Initialize the class with template data to extract functions with Function URLs.

        Parameters
        ----------
        stacks : List[Stack]
            List of stacks function URLs are extracted from
        cwd : str
            Optional working directory with respect to which we will resolve relative paths
        """
        self.stacks = stacks
        self.cwd = cwd
        self.function_urls = self._extract_function_urls()
        LOG.debug("%d Function URLs found in the template", len(self.function_urls))

    def get_all(self) -> Iterator[FunctionUrl]:
        """
        Yields all the Function URLs in the current Provider

        :yields function_url: a FunctionUrl object with configuration and properties
        """
        for function_url in self.function_urls:
            yield function_url

    def _extract_function_urls(self) -> List[FunctionUrl]:
        """
        Extracts all the function URLs from functions that have FunctionUrlConfig

        Returns
        -------
        List[FunctionUrl]
            List of Function URLs from functions with FunctionUrlConfig in template
        """
        function_urls = []

        # Use existing SamFunctionProvider to get all functions
        function_provider = SamFunctionProvider(stacks=self.stacks, use_raw_codeuri=True)

        # Method 1: SAM-style FunctionUrlConfig property
        for function in function_provider.get_all():
            if hasattr(function, "function_url_config") and function.function_url_config:
                function_url = FunctionUrl(
                    function_name=function.name,
                    config=function.function_url_config,
                    function_definition=function._asdict(),  # Convert NamedTuple to dict
                )
                function_urls.append(function_url)

        # Method 2: CDK-style AWS::Lambda::Url resources
        for stack in self.stacks:
            template_dict = stack.template_dict
            resources = template_dict.get("Resources", {})

            for resource_name, resource in resources.items():
                if resource.get("Type") == "AWS::Lambda::Url":
                    properties = resource.get("Properties", {})
                    target_function_arn = properties.get("TargetFunctionArn", {})

                    # Handle {"Ref": "FunctionName"} pattern
                    if isinstance(target_function_arn, dict) and "Ref" in target_function_arn:
                        function_name = target_function_arn["Ref"]

                        # Create config from Lambda URL properties
                        config = {"AuthType": properties.get("AuthType", "AWS_IAM"), "Cors": properties.get("Cors", {})}

                        function_url = FunctionUrl(
                            function_name=function_name,
                            config=config,
                            function_definition={"name": function_name},  # Minimal definition
                        )
                        function_urls.append(function_url)

        return function_urls
