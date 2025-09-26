"""
CLI command for "local start-function-urls" command
"""

import logging
from ssl import SSLError

import click

from samcli.cli.cli_config_file import ConfigProvider, configuration_option, save_params_option
from samcli.cli.main import aws_creds_options, pass_context, print_cmdline_args
from samcli.cli.main import common_options as cli_framework_options
from samcli.commands._utils.option_value_processor import process_image_options
from samcli.commands._utils.options import (
    generate_next_command_recommendation,
    hook_name_click_option,
    skip_prepare_infra_option,
    terraform_plan_file_option,
)
from samcli.commands.local.cli_common.options import (
    invoke_common_options,
    local_common_options,
    service_common_options,
    warm_containers_common_options,
)
from samcli.commands.local.lib.exceptions import InvalidIntermediateImageError
from samcli.commands.local.start_function_urls.core.command import InvokeFunctionUrlsCommand
from samcli.lib.telemetry.metric import track_command
from samcli.lib.utils.version_checker import check_newer_version
from samcli.local.docker.exceptions import ContainerNotStartableException, PortAlreadyInUse, ProcessSigTermException

LOG = logging.getLogger(__name__)

HELP_TEXT = """
Run Lambda functions with Function URLs locally for testing.
"""

DESCRIPTION = """
  Allows you to run Lambda functions with Function URLs locally for quick development & testing.
  When run in a directory that contains Lambda functions with FunctionUrlConfig in the SAM template,
  it will create local HTTP servers for each function on separate ports.
  
  Each function URL serves from the root path (/), matching AWS production behavior where
  each Function URL has its own unique domain. This port-based approach maintains production
  parity while enabling local testing.
"""


@click.command(
    "start-function-urls",
    cls=InvokeFunctionUrlsCommand,
    help=HELP_TEXT,
    short_help=HELP_TEXT,
    description=DESCRIPTION,
    requires_credentials=False,
    context_settings={"max_content_width": 120},
)
@configuration_option(provider=ConfigProvider(section="parameters"))
@terraform_plan_file_option
@hook_name_click_option(
    force_prepare=False, invalid_coexist_options=["t", "template-file", "template", "parameter-overrides"]
)
@skip_prepare_infra_option
@service_common_options(3001)
@click.option(
    "--port-range",
    default="3001-3010",
    help="Port range for auto-assignment (default: 3001-3010)",
)
@click.argument("function_name", required=False, metavar="FUNCTION_NAME")
@click.option(
    "--disable-authorizer",
    is_flag=True,
    default=False,
    help="Disable Lambda Authorizers and IAM authorization checks",
)
@invoke_common_options
@warm_containers_common_options
@local_common_options
@cli_framework_options
@aws_creds_options
@save_params_option
@pass_context
@track_command
@check_newer_version
@print_cmdline_args
def cli(
    ctx,
    # Function URLs specific options
    host,
    port,
    port_range,
    function_name,
    disable_authorizer,
    # Common Options for Lambda Invoke
    template_file,
    env_vars,
    debug_port,
    debug_args,
    debugger_path,
    container_env_vars,
    docker_volume_basedir,
    docker_network,
    log_file,
    layer_cache_basedir,
    skip_pull_image,
    force_image_build,
    parameter_overrides,
    save_params,
    config_file,
    config_env,
    warm_containers,
    shutdown,
    debug_function,
    container_host,
    container_host_interface,
    add_host,
    invoke_image,
    hook_name,
    skip_prepare_infra,
    terraform_plan_file,
    no_memory_limit,
):
    """
    `sam local start-function-urls` command entry point
    """
    # All logic must be implemented in the ``do_cli`` method. This helps with easy unit testing
    do_cli(
        ctx,
        host,
        port,
        port_range,
        function_name,
        disable_authorizer,
        template_file,
        env_vars,
        debug_port,
        debug_args,
        debugger_path,
        container_env_vars,
        docker_volume_basedir,
        docker_network,
        log_file,
        layer_cache_basedir,
        skip_pull_image,
        force_image_build,
        parameter_overrides,
        warm_containers,
        shutdown,
        debug_function,
        container_host,
        container_host_interface,
        add_host,
        invoke_image,
        hook_name,
        no_memory_limit,
    )  # pragma: no cover


def do_cli(  # pylint: disable=R0914
    ctx,
    host,
    port,
    port_range,
    function_name,
    disable_authorizer,
    template,
    env_vars,
    debug_port,
    debug_args,
    debugger_path,
    container_env_vars,
    docker_volume_basedir,
    docker_network,
    log_file,
    layer_cache_basedir,
    skip_pull_image,
    force_image_build,
    parameter_overrides,
    warm_containers,
    shutdown,
    debug_function,
    container_host,
    container_host_interface,
    add_host,
    invoke_image,
    hook_name,
    no_mem_limit,
):
    """
    Implementation of the ``cli`` method, just separated out for unit testing purposes
    """

    from samcli.commands.exceptions import UserException
    from samcli.commands.local.cli_common.invoke_context import InvokeContext
    from samcli.commands.local.lib.exceptions import NoFunctionUrlsDefined, OverridesNotWellDefinedError
    from samcli.commands.local.lib.local_function_url_service import LocalFunctionUrlService
    from samcli.commands.validate.lib.exceptions import InvalidSamDocumentException
    from samcli.lib.providers.exceptions import InvalidLayerReference
    from samcli.local.docker.lambda_debug_settings import DebuggingNotSupported

    LOG.debug("local start-function-urls command is called")

    processed_invoke_images = process_image_options(invoke_image)

    # Pass all inputs to setup necessary context to invoke function locally.
    # Handler exception raised by the processor for invalid args and print errors

    try:
        with InvokeContext(
            template_file=template,
            function_identifier=None,  # Don't scope to one particular function
            env_vars_file=env_vars,
            docker_volume_basedir=docker_volume_basedir,
            docker_network=docker_network,
            log_file=log_file,
            skip_pull_image=skip_pull_image,
            debug_ports=debug_port,
            debug_args=debug_args,
            debugger_path=debugger_path,
            container_env_vars_file=container_env_vars,
            parameter_overrides=parameter_overrides,
            layer_cache_basedir=layer_cache_basedir,
            force_image_build=force_image_build,
            aws_region=ctx.region if ctx else None,
            aws_profile=ctx.profile if ctx else None,
            warm_container_initialization_mode=warm_containers,
            debug_function=debug_function,
            shutdown=shutdown,
            container_host=container_host,
            container_host_interface=container_host_interface,
            invoke_images=processed_invoke_images,
            add_host=add_host,
            no_mem_limit=no_mem_limit,
        ) as invoke_context:
            service = LocalFunctionUrlService(
                lambda_invoke_context=invoke_context,
                port=port,
                host=host,
                port_range=port_range,
                function_name=function_name,
                disable_authorizer=disable_authorizer,
            )
            service.start()
            if not hook_name:
                command_suggestions = generate_next_command_recommendation(
                    [
                        ("Validate SAM template", "sam validate"),
                        ("Test Function in the Cloud", "sam sync --stack-name {{stack-name}} --watch"),
                        ("Deploy", "sam deploy --guided"),
                    ]
                )
                click.secho(command_suggestions, fg="yellow")
    except SSLError as ex:
        raise UserException(f"SSL Error: {ex.strerror}", wrapped_from=ex.__class__.__name__) from ex
    except NoFunctionUrlsDefined as ex:
        raise UserException(
            "Template does not have any Functions with Function URLs configured", wrapped_from=ex.__class__.__name__
        ) from ex
    except (
        InvalidSamDocumentException,
        OverridesNotWellDefinedError,
        InvalidLayerReference,
        InvalidIntermediateImageError,
        DebuggingNotSupported,
        PortAlreadyInUse,
    ) as ex:
        raise UserException(str(ex), wrapped_from=ex.__class__.__name__) from ex
    except ContainerNotStartableException as ex:
        raise UserException(str(ex), wrapped_from=ex.__class__.__name__) from ex
    except ProcessSigTermException:
        LOG.debug("Successfully exited SIGTERM terminated process")
    except KeyboardInterrupt:
        LOG.info("Keyboard interrupt received")
    except Exception as ex:
        raise UserException(
            f"Error starting Function URL services: {str(ex)}", wrapped_from=ex.__class__.__name__
        ) from ex
