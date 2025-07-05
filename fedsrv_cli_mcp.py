#fedsrv_cli_mcp
import click
import json
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PromptStyle
import requests
from datetime import datetime
import colorama
from colorama import Fore, Style
from rapidfuzz import fuzz
from fedsrv_cli_fuzzy_matcher import fuzzy_match_query, get_context_words
from fedsrv_cli_api_client import test_connection
from fedsrv_cli_utils import estimate_tokens
from fedsrv_cli_token_logging import log_token_breakdown, log_token_content
from fedsrv_cli_kg_parser import load_knowledge_graph

colorama.init(autoreset=True)

def run_mcp_mode(context, session):
    """Run the MCP mode interactive loop."""
    mcp_history = InMemoryHistory()
    mcp_session = PromptSession(history=mcp_history, style=PromptStyle.from_dict({'prompt': 'bold'}))
    
    if context.verbose_mode >= 1:
        click.echo(f"{Style.BRIGHT}Now entering MCP Mode. In this mode, all text entered will be sent directly to the MCP as-is.{Style.RESET_ALL}")
    
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
    grok_ok = test_connection(context.grok_config, 'Grok AI Endpoint', grok_headers, context.grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
    mcp_ok = test_connection(context.mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, context.mcp_config.get('endpoint', ''))
    if grok_ok and context.verbose_mode >= 1:
        click.echo(f"{Style.BRIGHT}Connected to Grok AI Endpoint{Style.RESET_ALL}")
    if mcp_ok and context.verbose_mode >= 1:
        click.echo(f"{Style.BRIGHT}Connected to MCP AI Endpoint \"Little LLM\"{Style.RESET_ALL}")

    if not grok_ok:
        if context.verbose_mode >= 1:
            click.echo(f"{Fore.RED}No valid Grok-3 connection. Exiting MCP mode.{Style.RESET_ALL}")
        return

    if context.verbose_mode >= 1:
        click.echo(f"{Style.BRIGHT}To return to main menu, type /back. To exit CLI, type /exit.{Style.RESET_ALL}")
        click.echo(f"{Style.BRIGHT}Type /help for MCP mode commands.{Style.RESET_ALL}")

    in_test_mode = False
    while True:
        prompt_suffix = "|mcp|test>" if in_test_mode else "|mcp>"
        prompt = mcp_session.prompt([('class:prompt', f'fedsrv-cli{prompt_suffix} ')]).strip()
        if prompt:
            mcp_history.append_string(prompt)
        
        if prompt == "/help":
            click.echo(f"{Style.BRIGHT}MCP Mode Commands:{Style.RESET_ALL}")
            click.echo("- /help: Shows this MCP mode-specific help.")
            click.echo("- /show-tokens: Displays the current token breakdown (system, history, KG context, total) and content (in verbose mode 2).")
            click.echo("- /reload-kg: Reloads the knowledge graph from the configured endpoint.")
            click.echo("- /back: Returns to the main CLI menu (or to MCP mode from test mode).")
            click.echo("- /exit: Exits the CLI entirely.")
            click.echo("- /mode:verbose 0/1/2: Sets verbosity (0=standard, 1=verbose, 2=extreme, currently {}).".format(context.verbose_mode))
            click.echo("- /mode:test: Enters a mode for sending requests to Grok-3 and MCP services.")
            click.echo("- Any other input: Sends the request to the MCP service (in test mode).")
        elif prompt == "/show-tokens":
            log_token_breakdown(context)
            log_token_content(context)
        elif prompt == "/reload-kg":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Reloading Knowledge Graph...{Style.RESET_ALL}")
            jsonld_graph = load_knowledge_graph(kg_url=context.kg_url, verbose_mode=context.verbose_mode)
            context.kg_labels = []
            for item in jsonld_graph.get('@graph', []):
                if item.get('@type') == 'Class' and '@id' in item:
                    context.kg_labels.append(item['@id'])
            context.kg_context = ""  # Reset to empty
            context.jsonld_graph = jsonld_graph
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Knowledge Graph reloaded with {len(context.kg_labels)} class labels.{Style.RESET_ALL}")
        elif prompt == "/mode:verbose 0":
            context.verbose_mode = 0
            click.echo(f"{Style.BRIGHT}Verbose mode: Standard (0){Style.RESET_ALL}")
        elif prompt == "/mode:verbose 1":
            context.verbose_mode = 1
            click.echo(f"{Style.BRIGHT}Verbose mode: Verbose (1){Style.RESET_ALL}")
        elif prompt == "/mode:verbose 2":
            context.verbose_mode = 2
            click.echo(f"{Style.BRIGHT}Verbose mode: Extreme (2){Style.RESET_ALL}")
        elif prompt == "/mode:test" and not in_test_mode:
            in_test_mode = True
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Now entering Test Mode. Requests will be sent to Grok-3 and MCP services.{Style.RESET_ALL}")
                click.echo(f"{Style.BRIGHT}Type /back to return to MCP mode, or /exit to quit CLI.{Style.RESET_ALL}")
        elif prompt == "/back" and in_test_mode:
            in_test_mode = False
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Returning to MCP Mode.{Style.RESET_ALL}")
        elif prompt == "/back" and not in_test_mode:
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Connection to Grok AI Endpoint closed.{Style.RESET_ALL}")
                if mcp_ok:
                    click.echo(f"{Style.BRIGHT}Connection to MCP AI Endpoint \"Little LLM\" closed.{Style.RESET_ALL}")
            break
        elif prompt == "/exit":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
            return True  # Signal exit to main CLI
        elif in_test_mode:
            try:
                # Debug KG labels
                if context.verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}KG Labels Count: {len(context.kg_labels)}{Style.RESET_ALL}")
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}KG Labels: {context.kg_labels[:10]}{Style.RESET_ALL}")

                # Fuzzy match KG labels
                kg_matches, fuzzy_scores = fuzzy_match_query(prompt, context.kg_labels, verbose_mode=context.verbose_mode, fuzzy_threshold=context.fuzzy_threshold)
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}Fuzzy Match Scores (all labels):{Style.RESET_ALL}")
                    all_scores = [(label, fuzz.token_sort_ratio(prompt.lower(), label.lower())) for label in context.kg_labels]
                    all_scores.sort(key=lambda x: x[1], reverse=True)
                    for label, score in all_scores[:5]:  # Top 5 scores
                        click.echo(f"{Fore.YELLOW}  {label}: {score:.1f}{Style.RESET_ALL}")
                context.kg_context = ", ".join(str(m) for m in kg_matches) if kg_matches else ""
                if not isinstance(context.kg_context, str):
                    if context.verbose_mode >= 1:
                        click.echo(f"{Fore.RED}Invalid KG context type: {type(context.kg_context)}{Style.RESET_ALL}")
                    context.kg_context = ""
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}KG context: {context.kg_context or '<No KG tokens>'}{Style.RESET_ALL}")

                # Fuzzy match prior messages
                history_matches, fuzzy_matches = fuzzy_match_query(prompt, context.memory, key="content", verbose_mode=context.verbose_mode, fuzzy_threshold=context.fuzzy_threshold)
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
                    if len(context.memory) > context.max_history:
                        context.memory = context.memory[-context.max_history:]
                    log_token_breakdown(context)
                    log_token_content(context)

                if mcp_ok:
                    try:
                        # Parse Grok-3 response as JSON
                        mcp_payload = json.loads(content)
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}MCP request: {json.dumps(mcp_payload, indent=2)}{Style.RESET_ALL}")
                    except json.JSONDecodeError:
                        if context.verbose_mode >= 1:
                            click.echo(f"{Fore.RED}Invalid JSON from Grok-3, falling back to original query.{Style.RESET_ALL}")
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
                    if len(context.memory) > context.max_history:
                        context.memory = context.memory[-context.max_history:]
                    log_token_breakdown(context)
                    log_token_content(context)

            except Exception as e:
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.RED}API error details: {e}\nPayload: {json.dumps(payload, indent=2) if 'payload' in locals() else 'Not constructed'}{Style.RESET_ALL}")
                click.echo(f"{Fore.RED}Error communicating with API: {e}{Style.RESET_ALL}")
        else:
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Input ignored in MCP mode. Enter /mode:test to send requests.{Style.RESET_ALL}")
