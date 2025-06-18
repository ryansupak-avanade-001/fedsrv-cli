import click
import os
import json
import requests
import colorama
from colorama import Fore, Style
from dotenv import load_dotenv
import rdflib
from rapidfuzz import fuzz
from datetime import datetime
from io import StringIO
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PromptStyle

colorama.init(autoreset=True)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

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

def load_knowledge_graph(startup_prompts):
    """Load Knowledge Graph from startup-prompts where name='get-kg'."""
    kg_endpoint = None
    for prompt in startup_prompts:
        if prompt.get("name") == "get-kg" and "content" in prompt:
            kg_endpoint = prompt["content"]
            break

    if not kg_endpoint:
        click.echo(f"{Fore.YELLOW}No get-kg endpoint found in startup-prompts{Style.RESET_ALL}")
        return None

    graph = rdflib.Graph()
    try:
        if kg_endpoint.startswith(("http://", "https://")):
            response = requests.get(kg_endpoint, timeout=10)
            response.raise_for_status()
            kg_content = response.text
            graph.parse(StringIO(kg_content), format="turtle")
            click.echo(f"{Fore.YELLOW}Downloaded and loaded Knowledge Graph from {kg_endpoint}{Style.RESET_ALL}")
        elif os.path.exists(kg_endpoint):
            graph.parse(kg_endpoint, format="turtle")
            click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph from {kg_endpoint}{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.YELLOW}KG endpoint {kg_endpoint} is neither a valid URL nor local file{Style.RESET_ALL}")
            return None
        return graph
    except Exception as e:
        click.echo(f"{Fore.RED}Error loading Knowledge Graph: {e}{Style.RESET_ALL}")
        return None

def fuzzy_match_query(query, items, key=None, verbose_mode=False, fuzzy_threshold=70):
    """Fuzzy match query against a list of items (KG labels or messages)."""
    matches = []
    query = query.lower()
    for item in items:
        text = item.lower() if key is None else item[key].lower()
        score = fuzz.token_set_ratio(query, text)
        if score > fuzzy_threshold:
            matches.append((item, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    matched_items = [m[0] for m in matches[:5]]  # Limit to top 5 matches
    if verbose_mode:
        click.echo(f"{Fore.YELLOW}Fuzzy matches (score > {fuzzy_threshold}): {[(item if key is None else item[key], score) for item, score in matches[:5]]}{Style.RESET_ALL}")
    return matched_items

def get_kg_labels(graph):
    """Extract labels from KG for fuzzy matching."""
    if not graph:
        return []
    labels = set()
    for s, p, o in graph:
        for term in (s, p, o):
            if isinstance(term, rdflib.Literal) or isinstance(term, rdflib.URIRef):
                label = str(term).split("#")[-1].split("/")[-1]
                if label:
                    labels.add(label)
    return list(labels)

def estimate_tokens(messages):
    """Estimate token count (1 char ≈ 1 token)."""
    return sum(len(json.dumps(msg)) for msg in messages)

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
    cli_config = config["mcp"].get("cli-config", {})

    # CLI settings from config
    version = cli_config.get("version", "0.1")
    max_history = cli_config.get("max-history", 10)
    token_limit = cli_config.get("max-tokens", 131072)
    fuzzy_threshold = cli_config.get("fuzzy-threshold", 70)
    verbose_mode = cli_config.get("verbose-mode", False)

    # Load Knowledge Graph from startup-prompts
    startup_prompts = grok_config.get("startup-prompts", [])
    kg_graph = load_knowledge_graph(startup_prompts)
    kg_labels = get_kg_labels(kg_graph)

    # Initialize memory
    memory = []  # List for [{"role": "user/assistant", "content": "text", "timestamp": "..."}]

    # Initialize command history
    main_history = InMemoryHistory()
    mcp_history = InMemoryHistory()
    main_session = PromptSession(history=main_history, style=prompt_style)
    mcp_session = PromptSession(history=mcp_history, style=prompt_style)

    # Get system prompt
    system_prompt = ""
    system_prompts = grok_config.get("system-prompts", [])
    if system_prompts and isinstance(system_prompts, list) and len(system_prompts) > 0:
        system_prompt = system_prompts[0].get("content", "")

    # Process startup-prompts (log only, excluding get-kg)
    if startup_prompts and isinstance(startup_prompts, list):
        for prompt in startup_prompts:
            if "content" in prompt and "name" not in prompt:
                click.echo(f"{Fore.YELLOW}Processing startup prompt: {prompt.get('content', '')}{Style.RESET_ALL}")

    # Connection notification for main CLI
    click.echo(f"{Style.BRIGHT}Connected to CLI{Style.RESET_ALL}")

    while True:
        command = main_session.prompt([('class:prompt', 'fedsrv-cli> ')]).strip()
        if command:
            main_history.append_string(command)
        
        if command == "help":
            click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
            click.echo("- help: Lists all commands and a usage summary of each.")
            click.echo("- mcp: Enters a mode that communicates directly with a FedSrv MCP Service via Natural Language.")
            click.echo("- version: Displays the CLI version.")
            click.echo("- mode:verbose on/off: Toggles verbose mode (currently {}).".format("ON" if verbose_mode else "OFF"))
            click.echo("- back: Returns to this main menu from a sub-mode.")
            click.echo("- exit: Exits the CLI entirely.")
        elif command == "version":
            click.echo(f"{Style.BRIGHT}> {version}{Style.RESET_ALL}")
        elif command == "mode:verbose on":
            verbose_mode = True
            click.echo(f"{Style.BRIGHT}Verbose mode: ON{Style.RESET_ALL}")
        elif command == "mode:verbose off":
            verbose_mode = False
            click.echo(f"{Style.BRIGHT}Verbose mode: OFF{Style.RESET_ALL}")
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
            
            # Connection tests and notifications
            grok_ok = test_connection(grok_config, 'Grok AI Endpoint "Big LLM"', grok_headers, grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
            mcp_ok = test_connection(mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, mcp_config.get('endpoint', ''))
            if grok_ok:
                click.echo(f"{Style.BRIGHT}Connected to Grok AI Endpoint \"Big LLM\"{Style.RESET_ALL}")
            if mcp_ok:
                click.echo(f"{Style.BRIGHT}Connected to MCP AI Endpoint \"Little LLM\"{Style.RESET_ALL}")

            if not grok_ok:
                click.echo(f"{Fore.RED}No valid Grok-3 connection. Exiting MCP mode.{Style.RESET_ALL}")
                continue

            click.echo(f"{Style.BRIGHT}To return to main menu, type back. To exit CLI, type exit.{Style.RESET_ALL}")
            click.echo(f"{Style.BRIGHT}Type help for MCP mode commands.{Style.RESET_ALL}")

            with requests.Session() as session:
                in_big_llm_mode = False
                while True:
                    prompt_suffix = "|mcp|big-llm>" if in_big_llm_mode else "|mcp>"
                    prompt = mcp_session.prompt([('class:prompt', f'fedsrv-cli{prompt_suffix} ')]).strip()
                    if prompt:
                        mcp_history.append_string(prompt)
                    
                    if prompt == "help":
                        click.echo(f"{Style.BRIGHT}MCP Mode Commands:{Style.RESET_ALL}")
                        click.echo("- help: Shows this MCP mode-specific help.")
                        click.echo("- back: Returns to the main CLI menu (or to MCP mode from big-llm mode).")
                        click.echo("- exit: Exits the CLI entirely.")
                        click.echo("- mode:verbose on/off: Toggles verbose mode (currently {}).".format("ON" if verbose_mode else "OFF"))
                        click.echo("- mode:big-llm: Enters a mode for sending requests to Grok-3 and MCP services.")
                        click.echo("- Any other input: Sends the request to the MCP service (in big-llm mode).")
                    elif prompt == "mode:verbose on":
                        verbose_mode = True
                        click.echo(f"{Style.BRIGHT}Verbose mode: ON{Style.RESET_ALL}")
                    elif prompt == "mode:verbose off":
                        verbose_mode = False
                        click.echo(f"{Style.BRIGHT}Verbose mode: OFF{Style.RESET_ALL}")
                    elif prompt == "mode:big-llm" and not in_big_llm_mode:
                        in_big_llm_mode = True
                        click.echo(f"{Style.BRIGHT}Now entering Big LLM Mode. Requests will be sent to Grok-3 and MCP services.{Style.RESET_ALL}")
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
                            # Fuzzy match KG labels
                            kg_matches = fuzzy_match_query(prompt, kg_labels, verbose_mode=verbose_mode, fuzzy_threshold=fuzzy_threshold)
                            kg_context = ", ".join(kg_matches) if kg_matches else "No KG matches"
                            if verbose_mode:
                                click.echo(f"{Fore.YELLOW}KG context: {kg_context}{Style.RESET_ALL}")

                            # Fuzzy match prior messages
                            history_matches = fuzzy_match_query(prompt, memory, key="content", verbose_mode=verbose_mode, fuzzy_threshold=fuzzy_threshold)
                            # Get last 3 messages (user/assistant pairs)
                            last_three = memory[-3:] if len(memory) >= 3 else memory

                            # Combine messages for payload
                            messages = [
                                {"role": "system", "content": f"{system_prompt}\nKG context: {kg_context}"},
                            ] + last_three + history_matches + [
                                {"role": "user", "content": prompt}
                            ]

                            # Check token limit
                            token_count = estimate_tokens(messages)
                            if verbose_mode:
                                click.echo(f"{Fore.YELLOW}Prompt token count: {token_count}{Style.RESET_ALL}")
                            if token_count > token_limit:
                                messages = messages[:1] + messages[-4:]  # Keep system, last 3, current query
                                if verbose_mode:
                                    click.echo(f"{Fore.YELLOW}Truncated prompt to {estimate_tokens(messages)} tokens{Style.RESET_ALL}")

                            if grok_ok:
                                payload = {
                                    "model": grok_config.get('model', 'grok-3'),
                                    "messages": messages
                                }
                                if verbose_mode:
                                    click.echo(f"{Fore.YELLOW}Grok-3 request: {json.dumps(payload, indent=2)}{Style.RESET_ALL}")
                                response = session.post(grok_config.get('endpoint'), json=payload, headers=grok_headers, timeout=10)
                                response.raise_for_status()
                                response_json = response.json()
                                if verbose_mode:
                                    click.echo(f"{Fore.YELLOW}Grok-3 response: {json.dumps(response_json, indent=2)}{Style.RESET_ALL}")
                                content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "No response")
                                click.echo(f"{Style.BRIGHT}> (Grok Response:) {content}{Style.RESET_ALL}")

                                # Store user prompt and response
                                memory.append({"role": "user", "content": prompt, "timestamp": datetime.now().isoformat()})
                                memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                                if len(memory) > max_history:
                                    memory = memory[-max_history:]

                            if mcp_ok:
                                mcp_payload = {"query": prompt}
                                if verbose_mode:
                                    click.echo(f"{Fore.YELLOW}MCP request: {json.dumps(mcp_payload, indent=2)}{Style.RESET_ALL}")
                                response = session.post(mcp_config.get('endpoint'), json=mcp_payload, headers=mcp_headers, timeout=10)
                                response.raise_for_status()
                                response_json = response.json()
                                if verbose_mode:
                                    click.echo(f"{Fore.YELLOW}MCP response: {json.dumps(response_json, indent=2)}{Style.RESET_ALL}")
                                content = response_json.get("result", "No response")
                                click.echo(f"{Style.BRIGHT}> (MCP Response:) {content}{Style.RESET_ALL}")

                                # Store MCP response
                                memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                                if len(memory) > max_history:
                                    memory = memory[-max_history:]

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
