#fedsrv_cli_main
import click
import json
import os
from dataclasses import dataclass
from datetime import datetime
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PromptStyle
import requests
import colorama
from colorama import Fore, Style
from fedsrv_cli_config import load_config
from fedsrv_cli_kg_parser import load_knowledge_graph
from fedsrv_cli_token_logging import log_token_breakdown, log_token_content
from fedsrv_cli_mcp import run_mcp_mode

colorama.init(autoreset=True)

SPLASH = r"""
   ____       ______            _______   ____
  / __/__ ___/ / __/____  _____/ ___/ /  /  _/
 / _// -_) _  /\ \/ __/ |/ /__/ /__/ /___/ /  
/_/  \__/\_,_/___/_/  |___/   \___/____/___/  
                                    version 0.1
"""

# Define prompt_toolkit style for the CLI prompt
prompt_style = PromptStyle.from_dict({
    'prompt': 'bold',
})

@dataclass
class CliContext:
    memory: list
    kg_context: str
    kg_labels: list
    combined_system_prompt: str
    verbose_mode: int
    token_limit: int
    fuzzy_threshold: float
    max_history: int
    grok_config: dict
    mcp_config: dict
    startup_prompts: list

@click.command()
def fedsrv_cli():
    """A CLI for interacting with FedSrv MCP Service."""
    click.echo(f"{Fore.GREEN}{Style.BRIGHT}{SPLASH}{Style.RESET_ALL}")
    click.echo(f"{Style.BRIGHT}Use /help if needed{Style.RESET_ALL}")
    
    # Load configuration
    config = load_config()
    grok_config = config["mcp"]["grok-ai"]  # Matches config.json: mcp.grok-ai
    mcp_config = config["mcp"]["mcp-service"]  # Expected but missing in provided config; preserved for logic
    cli_config = config["mcp"].get("cli", {})  # Matches config.json: mcp.cli (optional)
    kg_url = config.get("knowledge-graph", {}).get("url", "")  # Matches config.json: knowledge-graph.url

    # CLI settings from config
    version = cli_config.get("version", "0.1")  # Matches config.json: cli.version
    max_history = cli_config.get("max-history", 10)  # Matches config.json: knowledge-graph.max-history (also under cli in some configs)
    token_limit = cli_config.get("max-tokens", 131072)  # Matches config.json: mcp.grok-ai.max-tokens (also under cli in some configs)
    fuzzy_threshold = config.get("knowledge-graph", {}).get("fuzzy-threshold", 70)  # Matches config.json: knowledge-graph.fuzzy-threshold
    verbose_mode = cli_config.get("verbose-mode", 0)  # Matches config.json: cli.verbose-mode

    # Load Knowledge Graph from url
    jsonld_graph = load_knowledge_graph(kg_url=kg_url, verbose_mode=verbose_mode)
    
    # Extract kg_labels from JSON-LD graph
    kg_labels = []
    for item in jsonld_graph.get('@graph', []):
        if item.get('@type') == 'Class' and '@id' in item:
            kg_labels.append(item['@id'])

    # Initialize memory and KG context
    memory = []  # List for [{"role": "user/assistant", "content": "text", "timestamp": "..."}]
    kg_context = ""  # Empty at startup
    system_prompts = grok_config.get("system-prompts", [])  # Matches config.json: mcp.grok-ai.system-prompts
    startup_prompts = grok_config.get("startup-prompts", [])  # Expected but missing in provided config; preserved for logic
    combined_system_prompt = "\n".join(prompt.get("content", "") for prompt in system_prompts if isinstance(prompt, dict) and "content" in prompt) if system_prompts else ""

    # Initialize context
    context = CliContext(
        memory=memory,
        kg_context=kg_context,
        kg_labels=kg_labels,
        combined_system_prompt=combined_system_prompt,
        verbose_mode=verbose_mode,
        token_limit=token_limit,
        fuzzy_threshold=fuzzy_threshold,
        max_history=max_history,
        grok_config=grok_config,
        mcp_config=mcp_config,
        startup_prompts=startup_prompts
    )

    # Log tokens at startup (use configured verbose_mode)
    log_token_breakdown(context)
    log_token_content(context)

    # Initialize command history
    main_history = InMemoryHistory()
    main_session = PromptSession(history=main_history, style=prompt_style)

    # Connection notification for main CLI
    click.echo(f"{Style.BRIGHT}Connected to CLI{Style.RESET_ALL}")

    with requests.Session() as session:
        while True:
            command = main_session.prompt([('class:prompt', 'fedsrv-cli> ')]).strip()
            if command:
                main_history.append_string(command)
            
            if command.startswith("/"):
                if command == "/help":
                    click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
                    click.echo("- /help: Lists all commands and a usage summary of each.")
                    click.echo("- /mcp: Enters a mode that communicates with the FedSrv MCP Service.")
                    click.echo("- /version: Displays the CLI version.")
                    click.echo("- /mode:verbose 0/1/2: Sets verbosity (0=standard, 1=verbose, 2=extreme, currently {}).".format(context.verbose_mode))
                    click.echo("- /show-tokens: Displays the current token breakdown (system, history, KG context, total) and content (in verbose mode 2).")
                    click.echo("- /reload-kg: Reloads the knowledge graph from the configured endpoint.")
                    click.echo("- /back: Returns to this main menu from a sub-mode.")
                    click.echo("- /exit: Exits the CLI entirely.")
                elif command == "/version":
                    click.echo(f"{Style.BRIGHT}> {version}{Style.RESET_ALL}")
                elif command == "/mode:verbose 0":
                    context.verbose_mode = 0
                    click.echo(f"{Style.BRIGHT}Verbose mode: Standard (0){Style.RESET_ALL}")
                elif command == "/mode:verbose 1":
                    context.verbose_mode = 1
                    click.echo(f"{Style.BRIGHT}Verbose mode: Verbose (1){Style.RESET_ALL}")
                elif command == "/mode:verbose 2":
                    context.verbose_mode = 2
                    click.echo(f"{Style.BRIGHT}Verbose mode: Extreme (2){Style.RESET_ALL}")
                elif command == "/show-tokens":
                    original_verbose_mode = context.verbose_mode
                    context.verbose_mode = max(1, context.verbose_mode)  # Use at least Verbose Mode 1
                    log_token_breakdown(context)
                    log_token_content(context)
                    context.verbose_mode = original_verbose_mode  # Restore original setting
                elif command == "/reload-kg":
                    original_verbose_mode = context.verbose_mode
                    context.verbose_mode = max(1, context.verbose_mode)  # Use at least Verbose Mode 1
                    click.echo(f"{Style.BRIGHT}Reloading Knowledge Graph...{Style.RESET_ALL}")
                    jsonld_graph = load_knowledge_graph(kg_url=kg_url, verbose_mode=context.verbose_mode)
                    context.kg_labels = []
                    for item in jsonld_graph.get('@graph', []):
                        if item.get('@type') == 'Class' and '@id' in item:
                            kg_labels.append(item['@id'])
                    context.kg_context = ""  # Reset to empty
                    click.echo(f"{Style.BRIGHT}Knowledge Graph reloaded with {len(context.kg_labels)} class labels.{Style.RESET_ALL}")
                    context.verbose_mode = original_verbose_mode  # Restore original setting
                elif command == "/mcp":
                    if run_mcp_mode(context, session):  # Returns True if /exit was called
                        break
                elif command == "/back":
                    if context.verbose_mode >= 1:
                        click.echo(f"{Fore.YELLOW}Already at main menu.{Style.RESET_ALL}")
                elif command == "/exit":
                    if context.verbose_mode >= 1:
                        click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
                    break
                else:
                    click.echo(f"{Fore.RED}Invalid Command: {command}{Style.RESET_ALL}")
                    click.echo(f"{Style.BRIGHT}Type /help for available commands.{Style.RESET_ALL}")
            else:
                if context.verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Input ignored. Use / for commands.{Style.RESET_ALL}")

if __name__ == "__main__":
    fedsrv_cli()
