import click
import os
import json
import requests
import colorama
from colorama import Fore, Style
from dotenv import load_dotenv
import rdflib
from rapidfuzz import fuzz

colorama.init()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
VERSION = "0.1"

SPLASH = r"""
   ____       ______            _______   ____
  / __/__ ___/ / __/____  _____/ ___/ /  /  _/
 / _// -_) _  /\ \/ __/ |/ /__/ /__/ /___/ /  
/_/  \__/\_,_/___/_/  |___/   \___/____/___/  
                                    version 0.1
"""

def merge_dicts(source, target):
    """Recursively merge source dict into target, preserving target values unless source is blank."""
    for key, value in source.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            merge_dicts(value, target[key])
        elif value in ("", None, {}) and target.get(key):
            continue
        elif key not in target:
            target[key] = value
    return target

def load_config():
    """Load configuration from .env (CONFIG_JSON) first, then merge with config.json."""
    config = {}
    
    load_dotenv()
    config_json = os.getenv("CONFIG_JSON")
    if config_json:
        try:
            config = json.loads(config_json)
        except json.JSONDecodeError as e:
            click.echo(f"{Fore.RED}Error parsing CONFIG_JSON from .env: {e}{Style.RESET_ALL}")
            raise click.Abort()

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                json_config = json.load(f)
                config = merge_dicts(json_config, config)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            click.echo(f"{Fore.RED}Error loading config.json: {e}{Style.RESET_ALL}")
            raise click.Abort()

    if not config:
        click.echo(f"{Fore.RED}No configuration found: .env with CONFIG_JSON or config.json required{Style.RESET_ALL}")
        raise click.Abort()

    return config

def load_knowledge_graph(config):
    """Placeholder: Load Knowledge Graph using rdflib."""
    kg_path = config.get("mcp", {}).get("grok-ai-config", {}).get("kg-path", "")
    if kg_path and os.path.exists(kg_path):
        graph = rdflib.Graph()
        try:
            graph.parse(kg_path, format="turtle")
            click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph from {kg_path}{Style.RESET_ALL}")
            return graph
        except Exception as e:
            click.echo(f"{Fore.RED}Error loading Knowledge Graph: {e}{Style.RESET_ALL}")
    return None

def fuzzy_match_query(query, kg_labels):
    """Placeholder: Fuzzy match query terms to KG labels using rapidfuzz."""
    if kg_labels:
        click.echo(f"{Fore.YELLOW}Fuzzy matching query: {query} against {len(kg_labels)} KG labels{Style.RESET_ALL}")
    return []

def initialize_memory():
    """Stub: Initialize in-memory list for prompt/response history."""
    memory = []  # List to store [{"role": "user/assistant", "content": "text", "timestamp": "..."}]
    click.echo(f"{Fore.YELLOW}Initialized in-memory history storage{Style.RESET_ALL}")
    return memory

def test_connection(config, name, headers, endpoint, test_payload=None):
    try:
        response = requests.post(endpoint, json=test_payload or {}, headers=headers, timeout=5)
        response.raise_for_status()
        if response.json().get("choices") or response.json().get("result"):
            click.echo(f"{Style.BRIGHT}Connecting to {name}: SUCCESS{Style.RESET_ALL}")
            return True
        else:
            click.echo(f"{Fore.YELLOW}Connecting to {name}: FAILED (empty response){Style.RESET_ALL}")
            return False
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            click.echo(f"{Fore.RED}Connecting to {name}: FAILED (404 Not Found - check endpoint URL: {endpoint}){Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.YELLOW}Connecting to {name}: FAILED ({e}){Style.RESET_ALL}")
        return False
    except Exception as e:
        click.echo(f"{Fore.YELLOW}Connecting to {name}: FAILED ({e}){Style.RESET_ALL}")
        return False

@click.command()
def fedsrv_cli():
    """A CLI for interacting with FedSrv MCP Service."""
    click.echo(f"{Fore.GREEN}{Style.BRIGHT}{SPLASH}{Style.RESET_ALL}")
    
    config = load_config()
    grok_config = config["mcp"]["grok-ai-config"]
    mcp_config = config["mcp"]["mcp-service-config"]

    # Load Knowledge Graph (placeholder)
    kg_graph = load_knowledge_graph(config)

    # Initialize memory (stub)
    memory = initialize_memory()

    # Get system prompt (first from system-prompts if available, else empty string)
    system_prompt = ""
    system_prompts = grok_config.get("system-prompts", [])
    if system_prompts and isinstance(system_prompts, list) and len(system_prompts) > 0:
        system_prompt = system_prompts[0].get("content", "")

    # Check for startup-prompts and process if present (placeholder: log for now)
    startup_prompts = grok_config.get("startup-prompts", [])
    if startup_prompts and isinstance(startup_prompts, list):
        for prompt in startup_prompts:
            click.echo(f"{Fore.YELLOW}Processing startup prompt: {prompt.get('content', '')}{Style.RESET_ALL}")

    while True:
        command = click.prompt(f"{Style.BRIGHT}fedsrv-cli{Style.RESET_ALL}", type=str, prompt_suffix="> ").strip()
        
        if command == "help":
            click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
            click.echo("- help: Lists all commands and a usage summary of each.")
            click.echo("- mcp: Enters a mode that communicates directly with a FedSrv MCP Service via Natural Language.")
            click.echo("- version: Displays the CLI version.")
            click.echo("- back: Returns to this main menu from a sub-mode.")
            click.echo("- exit: Exits the CLI entirely.")
        elif command == "version":
            click.echo(f"{Style.BRIGHT}> {VERSION}{Style.RESET_ALL}")
        elif command == "mcp":
            click.echo(f"{Style.BRIGHT}Now entering MCP Mode. In this mode, all text entered will be sent directly to the MCP as-is.{Style.RESET_ALL}")
            
            grok_headers = {"Authorization": f"Bearer {grok_config.get('api_key')}", "Content-Type": "application/json"}
            mcp_headers = {"x-functions-key": mcp_config.get('api_key'), "Content-Type": "application/json"}
            grok_test_payload = {
                "model": grok_config.get('model', 'grok-3'),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "test"}
                ]
            }
            
            grok_ok = test_connection(grok_config, 'Grok AI Endpoint "Big LLM"', grok_headers, grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
            mcp_ok = test_connection(mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, mcp_config.get('endpoint', ''))

            if not grok_ok:
                click.echo(f"{Fore.RED}No valid Grok-3 connection. Exiting MCP mode.{Style.RESET_ALL}")
                continue

            click.echo(f"{Style.BRIGHT}To return to main menu, type back. To exit CLI, type exit.{Style.RESET_ALL}")
            click.echo(f"{Style.BRIGHT}Type help for MCP mode commands.{Style.RESET_ALL}")

            with requests.Session() as session:
                in_big_llm_mode = False
                while True:
                    prompt_suffix = "|mcp|big-llm>" if in_big_llm_mode else "|mcp>"
                    prompt = click.prompt(f"{Style.BRIGHT}fedsrv-cli{prompt_suffix}{Style.RESET_ALL}", type=str, prompt_suffix=" ").strip()
                    
                    if prompt == "help":
                        click.echo(f"{Style.BRIGHT}MCP Mode Commands:{Style.RESET_ALL}")
                        click.echo("- help: Shows this MCP mode-specific help.")
                        click.echo("- back: Returns to the main CLI menu (or to MCP mode from big-llm mode).")
                        click.echo("- exit: Exits the CLI entirely.")
                        click.echo("- mode:big-llm: Enters a mode showing only Grok-3 LLM output.")
                        click.echo("- Any other input: Sends the request directly to the MCP service (in big-llm mode).")
                    elif prompt == "mode:big-llm" and not in_big_llm_mode:
                        in_big_llm_mode = True
                        click.echo(f"{Style.BRIGHT}Now entering Big LLM Mode. Only Grok-3 output will be shown.{Style.RESET_ALL}")
                        click.echo(f"{Style.BRIGHT}Type back to return to MCP mode, or exit to quit CLI.{Style.RESET_ALL}")
                    elif prompt == "back" and in_big_llm_mode:
                        in_big_llm_mode = False
                        click.echo(f"{Style.BRIGHT}Returning to MCP Mode.{Style.RESET_ALL}")
                    elif prompt == "back" and not in_big_llm_mode:
                        click.echo(f"{Style.BRIGHT}Connection to Grok AI Endpoint \"Big LLM\" closed.{Style.RESET_ALL}")
                        if mcp_ok:
                            click.echo(f"{Style.BRIGHT}Connection to MCP AI Endpoint \"Little LLM\" closed.{Style.RESET_ALL}")
                        break
                    elif prompt == "exit":
                        click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
                        return
                    elif in_big_llm_mode:
                        try:
                            if grok_ok:
                                payload = {
                                    "model": grok_config.get('model', 'grok-3'),
                                    "messages": [
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": prompt}
                                    ]
                                }
                                response = session.post(grok_config.get('endpoint'), json=payload, headers=grok_headers, timeout=10)
                                response.raise_for_status()
                                content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "No response")
                                click.echo(f"{Style.BRIGHT}> (Grok Response:) {content}{Style.RESET_ALL}")
                            
                            if mcp_ok:
                                response = session.post(mcp_config.get('endpoint'), json={"query": prompt}, headers=mcp_headers, timeout=10)
                                response.raise_for_status()
                                content = response.json().get("result", "No response")
                                click.echo(f"{Style.BRIGHT}> (MCP Response:) {content}{Style.RESET_ALL}")
                        except Exception as e:
                            click.echo(f"{Fore.RED}Error communicating with API: {e}{Style.RESET_ALL}")
                    else:
                        click.echo(f"{Fore.YELLOW}Input ignored in MCP mode. Enter mode:big-llm to send requests.{Style.RESET_ALL}")
        elif command == "back":
            click.echo(f"{Fore.YELLOW}Already at main menu.{Style.RESET_ALL}")
        elif command == "exit":
            click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
            break
        else:
            click.echo(f"{Fore.RED}Unknown command: {command}{Style.RESET_ALL}")
            click.echo(f"{Style.BRIGHT}Type 'help' for available commands.{Style.RESET_ALL}")

if __name__ == "__main__":
    fedsrv_cli()
