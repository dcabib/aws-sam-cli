"""
`sam completion` command - Generate shell completion scripts for SAM CLI
"""

import os
from typing import Optional

import click
from click.shell_completion import get_completion_class

SUPPORTED_SHELLS = ["bash", "zsh", "fish"]


def detect_shell() -> Optional[str]:
    """
    Detect current shell from environment.

    Returns:
        Shell name if detected, None otherwise
    """
    shell_path = os.environ.get("SHELL", "")
    for shell in SUPPORTED_SHELLS:
        if shell in shell_path:
            return shell
    return None


@click.command("completion", short_help="Generate shell completion scripts.")
@click.argument("shell", type=click.Choice(SUPPORTED_SHELLS), required=False)
def cli(shell: Optional[str]) -> None:
    """
    Generate shell completion scripts for SAM CLI.

    Supported shells: bash, zsh, fish

    \b
    Examples:

      # Bash - add to ~/.bashrc or ~/.bash_profile
      eval "$(sam completion bash)"

      # Or save to completion directory (recommended for faster shell startup)
      sam completion bash > ~/.local/share/bash-completion/completions/sam

      # Zsh - add to ~/.zshrc
      eval "$(sam completion zsh)"

      # Or save to fpath (recommended)
      sam completion zsh > "${fpath[1]}/_sam"

      # Fish
      sam completion fish > ~/.config/fish/completions/sam.fish

      # Auto-detect shell (uses $SHELL environment variable)
      source <(sam completion)
    """
    if not shell:
        shell = detect_shell()
        if not shell:
            raise click.ClickException(
                f"Could not detect shell from $SHELL environment variable. "
                f"Please specify one of: {', '.join(SUPPORTED_SHELLS)}\n"
                f"Example: sam completion bash"
            )

    completion_class = get_completion_class(shell)
    if not completion_class:
        raise click.ClickException(f"Unsupported shell: {shell}")

    # Generate completion script using Click's template
    script = completion_class.source_template % {
        "complete_func": "_sam_completion",
        "complete_var": "_SAM_COMPLETE",
        "prog_name": "sam",
    }

    click.echo(script)
