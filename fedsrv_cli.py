import click
import os
import json
import requests
import colorama
from colorama import Fore, Style

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

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        click.echo(f"{Fore.RED}Error loading config: {e}{Style.RESET_ALL}")
        return {"mcp": {"grok-ai-config": {}, "mcp-service-config": {}}}

def test_connection(config, name, headers, endpoint, test_payload=None):
    try:
        response = requests.post(endpoint, json=test_payload or {}, headers=headers, timeout=5)
        response.raise_for_status()
        if response.json().get("choices") or response.json().get("result"):
            click.echo(f"{Style.BRIGHT}Connecting to {name}: SUCCESS{Style.RESET_ALL}")
            return True
        else:
            click.echo(f"{Fore.RED}Connecting to {name}: FAILED (empty response){Style.RESET_ALL}")
            return False
    except Exception as e:
        click.echo(f"{Fore.RED}Connecting to {name}: FAILED ({e}){Style.RESET_ALL}")
        return False

@click.command()
def fedsrv_cli():
    """A CLI for interacting with FedSrv MCP Service."""
    # Display green ASCII splash with VERSION right-justified to align with graphic
    splash = SPLASH.replace("$v", f"{VERSION:>37}")
    click.echo(f"{Fore.GREEN}{Style.BRIGHT}{splash}{Style.RESET_ALL}")
    
    config = load_config()
    grok_config = config["mcp"]["grok-ai-config"]
    mcp_config = config["mcp"]["mcp-service-config"]

    while True:
        command = click.prompt(f"{Style.BRIGHT}fedsrv-cli{Style.RESET_ALL}", type=str, prompt_suffix="> ").strip()
        
        if command == "help":
            click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
            click.echo("- help: Lists all commands and a usage summary of each.")
            click.echo("- mcp: Enters a mode that communicates directly with a FedSrv MCP Service via Natural Language.")
            click.echo("- version: Displays the CLI version.")
            click.echo("- exit: Exits the CLI.")
        elif command == "version":
            click.echo(f"{Style.BRIGHT}> {VERSION}{Style.RESET_ALL}")
        elif command == "mcp":
            click.echo(f"{Style.BRIGHT}Now entering MCP Mode. In this mode, all text entered will be sent directly to the MCP as-is.{Style.RESET_ALL}")
            
            grok_headers = {"Authorization": f"Bearer {grok_config.get('api_key')}", "Content-Type": "application/json"}
            mcp_headers = {"x-functions-key": mcp_config.get('api_key'), "Content-Type": "application/json"}
            grok_test_payload = {"model": grok_config.get('model', 'grok-3'), "messages": [{"role": "user", "content": "test"}]}
            
            grok_ok = test_connection(grok_config, 'Grok AI Endpoint "Big LLM"', grok_headers, grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
            mcp_ok = test_connection(mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, mcp_config.get('endpoint', ''))

            if not (grok_ok or mcp_ok):
                click.echo(f"{Fore.RED}No valid connections. Exiting MCP mode.{Style.RESET_ALL}")
                continue

            click.echo(f"{Style.BRIGHT}To leave MCP Mode, type exit or back (as the only thing on a line).{Style.RESET_ALL}")

            with requests.Session() as session:
                while True:
                    prompt = click.prompt(f"{Style.BRIGHT}fedsrv-cli|mcp{Style.RESET_ALL}", type=str, prompt_suffix="> ").strip()
                    
                    if prompt in ("exit", "back") and not (prompt.startswith("'") or prompt.startswith('"')):
                        click.echo(f"{Style.BRIGHT}Connection to Grok AI Endpoint \"Big LLM\" closed.{Style.RESET_ALL}")
                        click.echo(f"{Style.BRIGHT}Connection to MCP AI Endpoint \"Little LLM\" closed.{Style.RESET_ALL}")
                        break
                    
                    try:
                        if grok_ok:
                            payload = {"model": grok_config.get('model', 'grok-3'), "messages": [{"role": "user", "content": prompt}]}
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
        elif command == "exit":
            click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
            break
        else:
            click.echo(f"{Fore.RED}Unknown command: {command}{Style.RESET_ALL}")
            click.echo(f"{Style.BRIGHT}Type 'help' for available commands.{Style.RESET_ALL}")

if __name__ == "__main__":
    fedsrv_cli()