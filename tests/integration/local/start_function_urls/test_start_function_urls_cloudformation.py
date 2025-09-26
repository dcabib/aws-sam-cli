"""
Integration tests for sam local start-function-urls command with CloudFormation templates
Using standard CloudFormation templates with AWS::Lambda::Function resources.
"""

from unittest import skipIf

import requests

from tests.integration.local.start_function_urls.start_function_urls_integ_base import (
    WritableStartFunctionUrlIntegBaseClass,
)
from tests.testing_utils import (
    RUN_BY_CANARY,
    RUNNING_ON_CI,
    RUNNING_TEST_FOR_MASTER_ON_CI,
)


@skipIf(
    (RUNNING_ON_CI and not RUN_BY_CANARY) and not RUNNING_TEST_FOR_MASTER_ON_CI,
    "Skip integration tests on CI unless running canary or master",
)
class TestStartFunctionUrlsCloudFormation(WritableStartFunctionUrlIntegBaseClass):
    """
    Integration tests for start-function-urls with CloudFormation templates
    """

    # SAM template (which extends CloudFormation) to support CodeUri
    template_content = """
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Resources:
  CloudFormationFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ./
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
            'message': 'Hello from CloudFormation Function URL!',
            'source': 'cloudformation'
        })
    }
"""

    def test_cloudformation_function_url_basic(self):
        """Test basic Function URL with CloudFormation template"""
        # Start service
        self.assertTrue(
            self.start_function_urls(self.template),
            "Failed to start Function URLs service with CloudFormation template",
        )

        # Test GET request
        response = requests.get(f"{self.url}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["message"], "Hello from CloudFormation Function URL!")
        self.assertEqual(data["source"], "cloudformation")


#     def test_cloudformation_multiple_function_urls(self):
#         """Test multiple Function URLs in CloudFormation template"""
#         # SAM template with multiple functions
#         cf_multi_template = """
# AWSTemplateFormatVersion: '2010-09-09'
# Transform: AWS::Serverless-2016-10-31
# Resources:
#   ApiFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: api.handler
#       Runtime: python3.9
#       FunctionUrlConfig:
#         AuthType: NONE
#   WorkerFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: worker.handler
#       Runtime: python3.9
#       FunctionUrlConfig:
#         AuthType: AWS_IAM
#   PublicFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: public.handler
#       Runtime: python3.9
#       FunctionUrlConfig:
#         AuthType: NONE
#         Cors:
#           AllowOrigins:
#             - "*"
#           AllowMethods:
#             - "*"
# """
#
#         api_content = """
# import json
#
# def handler(event, context):
#     return {
#         'statusCode': 200,
#         'body': json.dumps({'function': 'ApiFunction', 'type': 'api'})
#     }
# """
#
#         worker_content = """
# import json
#
# def handler(event, context):
#     return {
#         'statusCode': 200,
#         'body': json.dumps({'function': 'WorkerFunction', 'type': 'worker'})
#     }
# """
#
#         public_content = """
# import json
#
# def handler(event, context):
#     return {
#         'statusCode': 200,
#         'body': json.dumps({'function': 'PublicFunction', 'type': 'public'})
#     }
# """
#
#         with tempfile.TemporaryDirectory() as temp_dir:
#             # Write SAM template
#             template_path = os.path.join(temp_dir, "cf-multi-template.yaml")
#             with open(template_path, "w") as f:
#                 f.write(cf_multi_template)
#
#             # Write function codes
#             with open(os.path.join(temp_dir, "api.py"), "w") as f:
#                 f.write(api_content)
#             with open(os.path.join(temp_dir, "worker.py"), "w") as f:
#                 f.write(worker_content)
#             with open(os.path.join(temp_dir, "public.py"), "w") as f:
#                 f.write(public_content)
#
#             # Start service with port range
#             base_port = int(self.port)
#             self.assertTrue(
#                 self.start_function_urls(template_path, extra_args=f"--port-range {base_port}-{base_port+10}"),
#                 "Failed to start Function URLs service with multiple CloudFormation functions",
#             )
#
#             # Test that functions are accessible
#             found_functions = []
#             for port_offset in range(10):
#                 try:
#                     response = requests.get(f"http://{self.host}:{base_port + port_offset}/", timeout=1)
#                     if response.status_code == 200:
#                         data = response.json()
#                         if "function" in data:
#                             found_functions.append(data["function"])
#                     elif response.status_code == 403:
#                         # AWS_IAM protected function
#                         found_functions.append("Protected")
#                 except Exception:
#                     pass
#
#             self.assertGreater(len(found_functions), 0, "No CloudFormation functions were accessible")
#
#     def test_cloudformation_function_url_with_layers(self):
#         """Test Function URL with Lambda layers in CloudFormation"""
#         # SAM template with layers
#         cf_layer_template = """
# AWSTemplateFormatVersion: '2010-09-09'
# Transform: AWS::Serverless-2016-10-31
# Resources:
#   SharedLayer:
#     Type: AWS::Serverless::LayerVersion
#     Properties:
#       LayerName: SharedLayer
#       ContentUri: ./layer
#       CompatibleRuntimes:
#         - python3.9
#   LayerFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: layer_func.handler
#       Runtime: python3.9
#       Layers:
#         - !Ref SharedLayer
#       FunctionUrlConfig:
#         AuthType: NONE
# """
#
#         layer_function_content = """
# import json
#
# def handler(event, context):
#     # Try to import from layer
#     try:
#         from shared import utils
#         has_layer = True
#         layer_message = utils.get_message() if hasattr(utils, 'get_message') else "Layer imported"
#     except ImportError:
#         has_layer = False
#         layer_message = "Layer not available"
#
#     return {
#         'statusCode': 200,
#         'body': json.dumps({
#             'has_layer': has_layer,
#             'layer_message': layer_message
#         })
#     }
# """
#
#         layer_utils_content = """
# def get_message():
#     return "Hello from CloudFormation Layer!"
# """
#
#         with tempfile.TemporaryDirectory() as temp_dir:
#             # Write SAM template
#             template_path = os.path.join(temp_dir, "cf-layer-template.yaml")
#             with open(template_path, "w") as f:
#                 f.write(cf_layer_template)
#
#             # Write function code
#             with open(os.path.join(temp_dir, "layer_func.py"), "w") as f:
#                 f.write(layer_function_content)
#
#             # Create layer structure
#             layer_dir = os.path.join(temp_dir, "layer", "python", "shared")
#             os.makedirs(layer_dir)
#             with open(os.path.join(layer_dir, "__init__.py"), "w") as f:
#                 f.write("")
#             with open(os.path.join(layer_dir, "utils.py"), "w") as f:
#                 f.write(layer_utils_content)
#
#             # Start service
#             self.assertTrue(
#                 self.start_function_urls(template_path, timeout=45),
#                 "Failed to start Function URLs service with CloudFormation layers",
#             )
#
#             # Give the service time to fully initialize and read all files
#             time.sleep(2)
#
#             # Test that layer is accessible
#             response = requests.get(f"{self.url}/")
#             self.assertEqual(response.status_code, 200)
#             data = response.json()
#             # Note: Layer might not work in local mode, so we just check the response
#             self.assertIn("has_layer", data)
#             self.assertIn("layer_message", data)
#
#     @parameterized.expand(
#         [
#             ("RESPONSE_STREAM",),
#             ("BUFFERED",),
#         ]
#     )
#     def test_cloudformation_function_url_invoke_modes(self, invoke_mode):
#         """Test Function URL with different invoke modes in CloudFormation"""
#         # SAM template with specific invoke mode
#         cf_invoke_template = f"""
# AWSTemplateFormatVersion: '2010-09-09'
# Transform: AWS::Serverless-2016-10-31
# Resources:
#   InvokeFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: invoke.handler
#       Runtime: python3.9
#       FunctionUrlConfig:
#         AuthType: NONE
#         InvokeMode: {invoke_mode}
# """
#
#         invoke_function_content = """
# import json
# import time
#
# def handler(event, context):
#     # Simulate different response based on invoke mode
#     invoke_mode = event.get('requestContext', {}).get('functionUrl', {}).get('invokeMode', 'BUFFERED')
#
#     if invoke_mode == 'RESPONSE_STREAM':
#         # Simulate streaming response
#         chunks = []
#         for i in range(3):
#             chunks.append(json.dumps({'chunk': i, 'timestamp': time.time()}))
#         return {
#             'statusCode': 200,
#             'headers': {'Content-Type': 'application/x-ndjson'},
#             'body': '\\n'.join(chunks)
#         }
#     else:
#         # Buffered response
#         return {
#             'statusCode': 200,
#             'body': json.dumps({
#                 'message': 'Buffered response',
#                 'invoke_mode': 'BUFFERED'
#             })
#         }
# """
#
#         with tempfile.TemporaryDirectory() as temp_dir:
#             # Write SAM template
#             template_path = os.path.join(temp_dir, "cf-invoke-template.yaml")
#             with open(template_path, "w") as f:
#                 f.write(cf_invoke_template)
#
#             # Write function code
#             with open(os.path.join(temp_dir, "invoke.py"), "w") as f:
#                 f.write(invoke_function_content)
#
#             # Start service
#             self.assertTrue(
#                 self.start_function_urls(template_path),
#                 f"Failed to start Function URLs service with CloudFormation {invoke_mode} mode",
#             )
#
#             # Test request
#             response = requests.get(f"{self.url}/")
#             self.assertEqual(response.status_code, 200)
#             # Both modes should work in local testing
#
#     def test_cloudformation_function_url_with_vpc_config(self):
#         """Test Function URL with VPC configuration in CloudFormation"""
#         # SAM template with VPC config
#         cf_vpc_template = """
# AWSTemplateFormatVersion: '2010-09-09'
# Transform: AWS::Serverless-2016-10-31
# Resources:
#   VpcFunction:
#     Type: AWS::Serverless::Function
#     Properties:
#       CodeUri: ./
#       Handler: vpc.handler
#       Runtime: python3.9
#       VpcConfig:
#         SecurityGroupIds:
#           - sg-12345678
#         SubnetIds:
#           - subnet-12345678
#           - subnet-87654321
#       FunctionUrlConfig:
#         AuthType: NONE
# """
#
#         vpc_function_content = """
# import json
# import socket
#
# def handler(event, context):
#     # Get network information
#     hostname = socket.gethostname()
#
#     return {
#         'statusCode': 200,
#         'body': json.dumps({
#             'message': 'Function with VPC config',
#             'hostname': hostname,
#             'vpc_configured': True
#         })
#     }
# """
#
#         with tempfile.TemporaryDirectory() as temp_dir:
#             # Write SAM template
#             template_path = os.path.join(temp_dir, "cf-vpc-template.yaml")
#             with open(template_path, "w") as f:
#                 f.write(cf_vpc_template)
#
#             # Write function code
#             with open(os.path.join(temp_dir, "vpc.py"), "w") as f:
#                 f.write(vpc_function_content)
#
#             # Start service (VPC config is ignored in local mode)
#             self.assertTrue(
#                 self.start_function_urls(template_path, timeout=45),
#                 "Failed to start Function URLs service with CloudFormation VPC config",
#             )
#
#             # Give the service time to fully initialize
#             time.sleep(3)
#
#             # Test that function works despite VPC config
#             response = requests.get(f"{self.url}/")
#             self.assertEqual(response.status_code, 200)
#
#             # Handle potential empty response
#             if response.text.strip():
#                 data = response.json()
#                 self.assertEqual(data["message"], "Function with VPC config")
#                 self.assertTrue(data["vpc_configured"])
#             else:
#                 # If response is empty, just verify we got a 200 status
#                 # VPC config doesn't affect local function execution
#                 self.assertTrue(True, "Function responded successfully despite VPC config")
#
#
# if __name__ == "__main__":
#     import unittest
#
#     unittest.main()
