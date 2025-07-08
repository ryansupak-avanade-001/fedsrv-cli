import click
import json
import os
import time
import re
from dataclasses import dataclass
from datetime import datetime
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PromptStyle
import colorama
import requests
from colorama import Fore, Style
from fedsrv_cli_config import load_config
from fedsrv_cli_kg_parser import load_knowledge_graph
from fedsrv_cli_token_logging import log_token_breakdown, log_token_content
from fedsrv_cli_mcp import run_mcp_mode

colorama.init(autoreset=True)

# Initialize log file
log_timestamp = int(time.time())
os.makedirs("logs", exist_ok=True)
log_file_path = f"logs/usage-{log_timestamp}.log"

def log_to_file(message):
    """Write a message to the log file, stripping ANSI codes and special characters."""
    clean_message = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|<0x[0-9a-fA-F]+>', '', str(message))
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}: {clean_message}\n")

# Wrap click.echo to log outputs
original_echo = click.echo
def custom_echo(message, **kwargs):
    original_echo(message, **kwargs)
    log_to_file(f"OUTPUT: {message}")

click.echo = custom_echo

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
    jsonld_graph: dict
    combined_system_prompt: str
    verbose_mode: int
    token_limit: int
    fuzzy_threshold: float
    max_history: int
    conversation_history: int
    grok_config: dict
    mcp_config: dict
    kg_url: str
    max_log_history: int
    log_file_path: str

@click.command()
def fedsrv_cli():
    """A CLI for interacting with FedSrv MCP Service."""
    click.echo(f"{Fore.GREEN}{Style.BRIGHT}{SPLASH}{Style.RESET_ALL}")
    click.echo(f"{Style.BRIGHT}Use /help if needed{Style.RESET_ALL}")
    
    # Load configuration
    config = load_config()
    grok_config = config["mcp"]["grok-ai"]
    mcp_config = config["mcp"]["mcp-service"]
    cli_config = config.get("cli", {})
    kg_url = config.get("knowledge-graph", {}).get("url", "")

    # CLI settings from config
    version = cli_config.get("version", "0.1")
    conversation_history = grok_config.get("conversation-history", 10)
    token_limit = cli_config.get("max-tokens", 131072)
    fuzzy_threshold = config.get("knowledge-graph", {}).get("fuzzy-threshold", 70)
    verbose_mode = cli_config.get("verbose-mode", 0)
    max_log_history = cli_config.get("max-history", 10)

    # Log verbose mode at startup
    verbose_mode_names = {0: "Standard", 1: "Verbose", 2: "Extreme", 3: "Debug"}
    verbose_mode_name = verbose_mode_names.get(verbose_mode, "Unknown")
    click.echo(f"{Fore.YELLOW}/mode:verbose is set to {verbose_mode} ({verbose_mode_name}){Style.RESET_ALL}")

    # Log max_log_history in Debug mode
    if verbose_mode >= 3:
        click.echo(f"{Fore.YELLOW}DEBUG: Max log history set to {max_log_history}{Style.RESET_ALL}")

    # Load Knowledge Graph
    jsonld_graph = load_knowledge_graph(kg_url=kg_url, verbose_mode=verbose_mode)
    
    # Initialize memory and KG context
    memory = []
    kg_context = ""
    system_prompts = grok_config.get("system-prompts", [])
    combined_system_prompt = "\n".join(prompt.get("content", "") for prompt in system_prompts if isinstance(prompt, dict) and "content" in prompt) if system_prompts else ""

    # Initialize context
    context = CliContext(
        memory=memory,
        kg_context=kg_context,
        jsonld_graph=jsonld_graph,
        combined_system_prompt=combined_system_prompt,
        verbose_mode=verbose_mode,
        token_limit=token_limit,
        fuzzy_threshold=fuzzy_threshold,
        max_history=max_log_history,
        conversation_history=conversation_history,
        grok_config=grok_config,
        mcp_config=mcp_config,
        kg_url=kg_url,
        max_log_history=max_log_history,
        log_file_path=log_file_path
    )

    # Log tokens at startup
    if verbose_mode >= 1:
        log_token_breakdown(context)
    else:
        log_token_breakdown(context)
    log_token_content(context)

    # Initialize command history
    main_history = InMemoryHistory()
    main_session = PromptSession(history=main_history, style=prompt_style)

    # Connection notification
    click.echo(f"{Style.BRIGHT}Connected to CLI{Style.RESET_ALL}")

    with requests.Session() as session:
        while True:
            command = main_session.prompt([('class:prompt', 'fedsrv-cli> ')]).strip()
            if command:
                main_history.append_string(command)
                log_to_file(f"INPUT: {command}")
            
            if command.startswith("/"):
                if command == "/help":
                    click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
                    click.echo("- /help: Lists all commands and a usage summary of each.")
                    click.echo("- /mcp: Enters a mode that communicates with the FedSrv MCP Service.")
                    click.echo("- /version: Displays the CLI version.")
                    click.echo("- /mode:verbose 0/1/2/3: Sets verbosity (0=standard, 1=verbose, 2=extreme, 3=debug, currently {}).".format(context.verbose_mode))
                    click.echo("- /show-tokens: Displays the current token breakdown and content.")
                    click.echo("- /reload-kg: Reloads the knowledge graph from the configured endpoint.")
                    click.echo("- /exit: Exits the CLI entirely.")
                elif command == "/mcp":
                    if run_mcp_mode(context, session, log_to_file):
                        log_files = [f for f in os.listdir("logs") if f.startswith("usage-") and f.endswith(".log")]
                        log_files.sort(key=lambda x: int(x.split("-")[1].split(".")[0]), reverse=True)
                        for old_file in log_files[context.max_log_history:]:
                            try:
                                os.remove(os.path.join("logs", old_file))
                                if context.verbose_mode >= 1:
                                    click.echo(f"{Fore.YELLOW}Deleted old log file: {old_file}{Style.RESET_ALL}")
                            except OSError as e:
                                if context.verbose_mode >= 1:
                                    click.echo(f"{Fore.RED}Failed to delete log file {old_file}: {str(e)}{Style.RESET_ALL}")
                        break
                elif command == "/version":
                    click.echo(f"{Style.BRIGHT}fedsrv-cli version {version}{Style.RESET_ALL}")
                elif command.startswith("/mode:verbose"):
                    try:
                        new_mode = int(command.split()[-1])
                        if new_mode in verbose_mode_names:
                            context.verbose_mode = new_mode
                            click.echo(f"{Fore.YELLOW}Verbose mode set to {new_mode} ({verbose_mode_names[new_mode]}){Style.RESET_ALL}")
                        else:
                            click.echo(f"{Fore.RED}Invalid verbose mode. Use 0-3.{Style.RESET_ALL}")
                    except (ValueError, IndexError):
                        click.echo(f"{Fore.RED}Invalid format. Use /mode:verbose 0/1/2/3{Style.RESET_ALL}")
                elif command == "/show-tokens":
                    original_verbose = context.verbose_mode
                    context.verbose_mode = max(1, context.verbose_mode)
                    log_token_breakdown(context)
                    log_token_content(context)
                    context.verbose_mode = original_verbose
                elif command == "/reload-kg":
                    original_verbose = context.verbose_mode
                    context.verbose_mode = max(1, context.verbose_mode)
                    context.jsonld_graph = load_knowledge_graph(kg_url=kg_url, verbose_mode=context.verbose_mode)
                    context.verbose_mode = original_verbose
                    click.echo(f"{Fore.GREEN}Knowledge graph reloaded.{Style.RESET_ALL}")
                elif command == "/exit":
                    if context.verbose_mode >= 1:
                        click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
                        click.echo(f"{Fore.YELLOW}Usage log written to {log_file_path}{Style.RESET_ALL}")
                    log_files = [f for f in os.listdir("logs") if f.startswith("usage-") and f.endswith(".log")]
                    log_files.sort(key=lambda x: int(x.split("-")[1].split(".")[0]), reverse=True)
                    if context.verbose_mode >= 1 and log_files[context.max_log_history:]:
                        click.echo(f"{Fore.YELLOW}Cleaning up log files exceeding max-history ({context.max_log_history})...{Style.RESET_ALL}")
                    for old_file in log_files[context.max_log_history:]:
                        try:
                            os.remove(os.path.join("logs", old_file))
                            if context.verbose_mode >= 1:
                                click.echo(f"{Fore.YELLOW}Deleted old log file: {old_file}{Style.RESET_ALL}")
                        except OSError as e:
                            if context.verbose_mode >= 1:
                                click.echo(f"{Fore.RED}Failed to delete log file {old_file}: {str(e)}{Style.RESET_ALL}")
                    break
                else:
                    click.echo(f"{Fore.RED}Invalid Command: {command}{Style.RESET_ALL}")
                    click.echo(f"{Style.BRIGHT}Type /help for available commands.{Style.RESET_ALL}")
            else:
                if context.verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Input ignored. Use / for commands.{Style.RESET_ALL}")

if __name__ == "__main__":
    fedsrv_cli()
