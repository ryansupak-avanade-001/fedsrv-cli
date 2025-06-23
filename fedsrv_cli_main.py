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
from fedsrv_cli_fuzzy_matcher import fuzzy_match_query, get_context_words
from fedsrv_cli_api_client import test_connection
from fedsrv_cli_utils import estimate_tokens
from fedsrv_cli_token_logging import log_token_breakdown, log_token_content

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
    grok_config: dict
    mcp_config: dict
    startup_prompts: list

@click.command()
def fedsrv_cli():
    """A CLI for interacting with FedSrv MCP Service."""
    click.echo(f"{Fore.GREEN}{Style.BRIGHT}{SPLASH}{Style.RESET_ALL}")
    click.echo(f"{Style.BRIGHT}Use /help if needed{Style.RESET_ALL}")
    
    config = load_config()
    grok_config = config["mcp"]["grok-ai-config"]
    mcp_config = config["mcp"]["mcp-service-config"]
    cli_config = config["mcp"].get("cli-config", {})

    # CLI settings from config
    version = cli_config.get("version", "0.1")
    max_history = cli_config.get("max-history", 10)
    token_limit = cli_config.get("max-tokens", 131072)
    fuzzy_threshold = cli_config.get("fuzzy-threshold", 70)
    verbose_mode = cli_config.get("verbose-mode", 0)

    # Load Knowledge Graph from startup-prompts
    startup_prompts = grok_config.get("startup-prompts", [])
    jsonld_graph = load_knowledge_graph(startup_prompts, verbose_mode=verbose_mode)
    
    # Extract kg_labels from JSON-LD graph
    kg_labels = []
    for item in jsonld_graph.get('@graph', []):
        if item.get('@type') == 'Class' and '@id' in item:
            kg_labels.append(item['@id'])

    # Initialize memory and KG context
    memory = []  # List for [{"role": "user/assistant", "content": "text", "timestamp": "..."}]
    kg_context = ""  # Empty at startup
    system_prompts = grok_config.get("system-prompts", [])
    combined_system_prompt = "\n".join(prompt.get("content", "") for prompt in system_prompts if isinstance(prompt, dict) and "content" in prompt) if system_prompts else ""

    # Initialize context
    context = CliContext(
        memory=memory,
        kg_context=kg_context,
        kg_labels=kg_labels,
        combined_system_prompt=combined_system_prompt,
        verbose_mode=verbose_mode,
        token_limit=token_limit,
        grok_config=grok_config,
        mcp_config=mcp_config,
        startup_prompts=startup_prompts
    )

    # Log tokens at startup
    log_token_breakdown(context)
    log_token_content(context)

    # Initialize command history
    main_history = InMemoryHistory()
    mcp_history = InMemoryHistory()
    main_session = PromptSession(history=main_history, style=prompt_style)
    mcp_session = PromptSession(history=mcp_history, style=prompt_style)

    # Connection notification for main CLI
    click.echo(f"{Style.BRIGHT}Connected to CLI{Style.RESET_ALL}")

    while True:
        command = main_session.prompt([('class:prompt', 'fedsrv-cli> ')]).strip()
        if command:
            main_history.append_string(command)
        
        if command == "/help":
            click.echo(f"{Style.BRIGHT}Available Commands:{Style.RESET_ALL}")
            click.echo("- /help: Lists all commands and a usage summary of each.")
            click.echo("- /mcp: Enters a mode that communicates directly with a FedSrv MCP Service via Natural Language.")
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
            log_token_breakdown(context)
            log_token_content(context)
        elif command == "/reload-kg":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Reloading Knowledge Graph...{Style.RESET_ALL}")
            jsonld_graph = load_knowledge_graph(context.startup_prompts, verbose_mode=context.verbose_mode)
            context.kg_labels = []
            for item in jsonld_graph.get('@graph', []):
                if item.get('@type') == 'Class' and '@id' in item:
                    context.kg_labels.append(item['@id'])
            context.kg_context = ""  # Reset to empty
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Knowledge Graph reloaded with {len(context.kg_labels)} class labels.{Style.RESET_ALL}")
        elif command == "/mcp":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Now entering MCP Mode. In this mode, all text entered will be sent directly to the MCP as-is.{Style.RESET_ALL}")
            # Process startup-prompts (log only, excluding get-kg)
            if context.startup_prompts and isinstance(context.startup_prompts, list):
                for prompt in context.startup_prompts:
                    if "content" in prompt and "name" not in prompt:
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}Processing startup prompt: {prompt.get('content', '')}{Style.RESET_ALL}")
            
            grok_headers = {"Authorization": f"Bearer {context.grok_config.get('api_key')}", "Content-Type": "application/json"}
            mcp_headers = {"x-functions-key": context.mcp_config.get('api_key'), "Content-Type": "application/json"}
            grok_test_payload = {
                "model": context.grok_config.get('model', 'grok-3'),
                "messages": [
                    {"role": "system", "content": context.combined_system_prompt},
                    {"role": "user", "content": "test"}
                ]
            }
            
            # Connection tests and notifications
            grok_ok = test_connection(context.grok_config, 'Grok AI Endpoint "Big LLM"', grok_headers, context.grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
            mcp_ok = test_connection(context.mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, context.mcp_config.get('endpoint', ''))
            if grok_ok and context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Connected to Grok AI Endpoint \"Big LLM\"{Style.RESET_ALL}")
            if mcp_ok and context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Connected to MCP AI Endpoint \"Little LLM\"{Style.RESET_ALL}")

            if not grok_ok:
                if context.verbose_mode >= 1:
                    click.echo(f"{Fore.RED}No valid Grok-3 connection. Exiting MCP mode.{Style.RESET_ALL}")
                continue

            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}To return to main menu, type /back. To exit CLI, type /exit.{Style.RESET_ALL}")
                click.echo(f"{Style.BRIGHT}Type /help for MCP mode commands.{Style.RESET_ALL}")

            with requests.Session() as session:
                in_big_llm_mode = False
                while True:
                    prompt_suffix = "|mcp|big-llm>" if in_big_llm_mode else "|mcp>"
                    prompt = mcp_session.prompt([('class:prompt', f'fedsrv-cli{prompt_suffix} ')]).strip()
                    if prompt:
                        mcp_history.append_string(prompt)
                    
                    if prompt == "/help":
                        click.echo(f"{Style.BRIGHT}MCP Mode Commands:{Style.RESET_ALL}")
                        click.echo("- /help: Shows this MCP mode-specific help.")
                        click.echo("- /back: Returns to the main CLI menu (or to MCP mode from big-llm mode).")
                        click.echo("- /exit: Exits the CLI entirely.")
                        click.echo("- /mode:verbose 0/1/2: Sets verbosity (0=standard, 1=verbose, 2=extreme, currently {}).".format(context.verbose_mode))
                        click.echo("- /mode:big-llm: Enters a mode for sending requests to Grok-3 and MCP services.")
                        click.echo("- Any other input: Sends the request to the MCP service (in big-llm mode).")
                    elif prompt == "/mode:verbose 0":
                        context.verbose_mode = 0
                        click.echo(f"{Style.BRIGHT}Verbose mode: Standard (0){Style.RESET_ALL}")
                    elif prompt == "/mode:verbose 1":
                        context.verbose_mode = 1
                        click.echo(f"{Style.BRIGHT}Verbose mode: Verbose (1){Style.RESET_ALL}")
                    elif prompt == "/mode:verbose 2":
                        context.verbose_mode = 2
                        click.echo(f"{Style.BRIGHT}Verbose mode: Extreme (2){Style.RESET_ALL}")
                    elif prompt == "/mode:big-llm" and not in_big_llm_mode:
                        in_big_llm_mode = True
                        if context.verbose_mode >= 1:
                            click.echo(f"{Style.BRIGHT}Now entering Big LLM Mode. Requests will be sent to Grok-3 and MCP services.{Style.RESET_ALL}")
                            click.echo(f"{Style.BRIGHT}Type /back to return to MCP mode, or /exit to quit CLI.{Style.RESET_ALL}")
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}Startup prompts:{Style.RESET_ALL}")
                            for prompt_entry in context.startup_prompts:
                                if isinstance(prompt_entry, dict):
                                    if "name" in prompt_entry and prompt_entry["name"] == "get-kg":
                                        click.echo(f"{Fore.YELLOW}  get-kg: {prompt_entry.get('content', '')}{Style.RESET_ALL}")
                                    elif "content" in prompt_entry:
                                        click.echo(f"{Fore.YELLOW}  content: {prompt_entry.get('content', '')}{Style.RESET_ALL}")
                    elif prompt == "/back" and in_big_llm_mode:
                        in_big_llm_mode = False
                        if context.verbose_mode >= 1:
                            click.echo(f"{Style.BRIGHT}Returning to MCP Mode.{Style.RESET_ALL}")
                    elif prompt == "/back" and not in_big_llm_mode:
                        if context.verbose_mode >= 1:
                            click.echo(f"{Style.BRIGHT}Connection to Grok AI Endpoint \"Big LLM\" closed.{Style.RESET_ALL}")
                            if mcp_ok:
                                click.echo(f"{Style.BRIGHT}Connection to MCP AI Endpoint \"Little LLM\" closed.{Style.RESET_ALL}")
                        break
                    elif prompt == "/exit":
                        if context.verbose_mode >= 1:
                            click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
                        return
                    elif in_big_llm_mode:
                        try:
                            # Fuzzy match KG labels
                            kg_matches, _ = fuzzy_match_query(prompt, context.kg_labels, verbose_mode=context.verbose_mode, fuzzy_threshold=fuzzy_threshold)
                            context.kg_context = ", ".join(str(m) for m in kg_matches) if kg_matches else ""
                            if not isinstance(context.kg_context, str):
                                if context.verbose_mode >= 1:
                                    click.echo(f"{Fore.RED}Invalid KG context type: {type(context.kg_context)}{Style.RESET_ALL}")
                                context.kg_context = ""
                            if context.verbose_mode >= 2:
                                click.echo(f"{Fore.YELLOW}KG context: {context.kg_context or '<No KG Matches>'}{Style.RESET_ALL}")

                            # Fuzzy match prior messages
                            history_matches, fuzzy_matches = fuzzy_match_query(prompt, context.memory, key="content", verbose_mode=context.verbose_mode, fuzzy_threshold=fuzzy_threshold)
                            # Get last 3 messages (user/assistant pairs)
                            last_three = context.memory[-3:] if len(context.memory) >= 3 else context.memory

                            # Log memory summary in verbose mode
                            if context.verbose_mode >= 2:
                                click.echo(f"{Fore.YELLOW}Conversation Memory prompts included:{Style.RESET_ALL}")
                                if last_three:
                                    click.echo(f"{Fore.YELLOW}  Recent messages (last 3):{Style.RESET_ALL}")
                                    for msg in last_three:
                                        first_words = " ".join(msg["content"].split()[:5])
                                        role = msg["role"].capitalize()
                                        click.echo(f"{Fore.YELLOW}    {role}: {first_words}...{Style.RESET_ALL}")
                                if history_matches:
                                    click.echo(f"{Fore.YELLOW}  Fuzzy matched messages:{Style.RESET_ALL}")
                                    for msg, (item, score) in zip(history_matches, fuzzy_matches):
                                        content = item["content"]
                                        matched_word = content.lower().split()[0]  # Approximate matched word
                                        before, after = get_context_words(content, matched_word)
                                        role = item["role"].capitalize()
                                        click.echo(f"{Fore.YELLOW}    {role}: {before} **{matched_word}** {after} (Score: {score:.1f}){Style.RESET_ALL}")

                            # Validate messages
                            messages = [
                                {"role": "system", "content": f"{context.combined_system_prompt}\nKG context: {context.kg_context}" if context.kg_context else context.combined_system_prompt},
                            ] + last_three + history_matches + [
                                {"role": "user", "content": prompt}
                            ]
                            for msg in messages:
                                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg or not isinstance(msg["content"], str):
                                    if context.verbose_mode >= 2:
                                        click.echo(f"{Fore.RED}Invalid message format in payload: {msg}{Style.RESET_ALL}")
                                    continue

                            # Log tokens before Big LLM request
                            log_token_breakdown(context, user_prompt=prompt)
                            log_token_content(context, user_prompt=prompt)

                            # Check token limit
                            token_count = estimate_tokens(messages)
                            if context.verbose_mode >= 2:
                                click.echo(f"{Fore.YELLOW}Prompt token count: {token_count}{Style.RESET_ALL}")
                            if token_count > context.token_limit:
                                messages = messages[:1] + messages[-4:]  # Keep system, last 3, current query
                                if context.verbose_mode >= 2:
                                    click.echo(f"{Fore.YELLOW}Truncated prompt to {estimate_tokens(messages)} tokens{Style.RESET_ALL}")

                            if grok_ok:
                                payload = {
                                    "model": context.grok_config.get('model', 'grok-3'),
                                    "messages": messages
                                }
                                if context.verbose_mode >= 2:
                                    click.echo(f"{Fore.YELLOW}Grok-3 request: {json.dumps(payload, indent=2)}{Style.RESET_ALL}")
                                response = session.post(context.grok_config.get('endpoint'), json=payload, headers=grok_headers, timeout=10)
                                response.raise_for_status()
                                response_json = response.json()
                                if context.verbose_mode >= 2:
                                    click.echo(f"{Fore.YELLOW}Grok-3 response: {json.dumps(response_json, indent=2)}{Style.RESET_ALL}")
                                content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "No response")
                                click.echo(f"{Style.BRIGHT}> (Grok Response:) {content}{Style.RESET_ALL}")

                                # Store user prompt and response
                                context.memory.append({"role": "user", "content": prompt, "timestamp": datetime.now().isoformat()})
                                context.memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                                if len(context.memory) > max_history:
                                    context.memory = context.memory[-max_history:]
                                log_token_breakdown(context)
                                log_token_content(context)

                            if mcp_ok:
                                mcp_payload = {"query": prompt}
                                if context.verbose_mode >= 2:
                                    click.echo(f"{Fore.YELLOW}MCP request: {json.dumps(mcp_payload, indent=2)}{Style.RESET_ALL}")
                                response = session.post(context.mcp_config.get('endpoint'), json=mcp_payload, headers=mcp_headers, timeout=10)
                                response.raise_for_status()
                                response_json = response.json()
                                if context.verbose_mode >= 2:
                                    click.echo(f"{Fore.YELLOW}MCP response: {json.dumps(response_json, indent=2)}{Style.RESET_ALL}")
                                content = response_json.get("result", "No response")
                                click.echo(f"{Style.BRIGHT}> (MCP Response:) {content}{Style.RESET_ALL}")

                                # Store MCP response
                                context.memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat()})
                                if len(context.memory) > max_history:
                                    context.memory = context.memory[-max_history:]
                                log_token_breakdown(context)
                                log_token_content(context)

                        except Exception as e:
                            if context.verbose_mode >= 2:
                                click.echo(f"{Fore.RED}API error details: {e}\nPayload: {json.dumps(payload, indent=2) if 'payload' in locals() else 'Not constructed'}{Style.RESET_ALL}")
                            click.echo(f"{Fore.RED}Error communicating with API: {e}{Style.RESET_ALL}")
                    else:
                        if context.verbose_mode >= 1:
                            click.echo(f"{Fore.YELLOW}Input ignored in MCP mode. Enter /mode:big-llm to send requests.{Style.RESET_ALL}")
        elif command == "/back":
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Already at main menu.{Style.RESET_ALL}")
        elif command == "/exit":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
            break
        else:
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.RED}Unknown command: {command}{Style.RESET_ALL}")
                click.echo(f"{Style.BRIGHT}Type /help for available commands.{Style.RESET_ALL}")

if __name__ == "__main__":
    fedsrv_cli()
