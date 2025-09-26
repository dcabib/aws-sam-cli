"""
Integration tests for start-function-urls with SAM templates
"""

from unittest import skipIf


from tests.integration.local.start_function_urls.start_function_urls_integ_base import (
    StartFunctionUrlIntegBaseClass,
)
from tests.testing_utils import (
    RUNNING_ON_CI,
    RUNNING_TEST_FOR_MASTER_ON_CI,
    RUN_BY_CANARY,
)


@skipIf(
    ((RUNNING_ON_CI and RUNNING_TEST_FOR_MASTER_ON_CI) or RUN_BY_CANARY),
    "Skip start-function-urls tests in CI/CD only",
)
class TestStartFunctionUrlsSAMTemplates(StartFunctionUrlIntegBaseClass):
    """
    Test Function URLs with SAM template configurations
    """

    template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  SAMFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: .
      Handler: main.handler
      Runtime: python3.9
      FunctionUrlConfig:
        AuthType: NONE
"""

    code_content = """
import json

def handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Hello from SAM Function URL!',
            'source': 'sam'
        })
    }
"""


#     def test_sam_function_url_basic(self):
#         """Test basic SAM Function URL configuration"""
#         # The service is already started by the base class
#         base_url = f"http://127.0.0.1:{self.__class__.port}"
#
#         # Test GET request
#         response = requests.get(f"{base_url}/")
#         self.assertEqual(response.status_code, 200)
#
#         data = response.json()
#         self.assertIn("message", data)
#         self.assertEqual(data["source"], "sam")
