#fedsrv_cli_mcp.py
#818b2c14-fb15-4899-bd5d-e622bbc391dd
import click
import json
import os
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style as PromptStyle
import requests
from datetime import datetime
import colorama
from colorama import Fore, Style
from fedsrv_cli_fuzzy_matcher import fuzzy_match_query, get_context_words
from fedsrv_cli_api_client import test_connection
from fedsrv_cli_utils import estimate_tokens
from fedsrv_cli_token_logging import log_token_breakdown, log_token_content
from fedsrv_cli_kg_parser import load_knowledge_graph
from fedsrv_cli_data_source_processor import process_data_sources

colorama.init(autoreset=True)

def run_mcp_mode(context, session, log_to_file):
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
    
    # Initialize matches with TTL for all data sources
    context.context_matches_with_ttl = {
        "kg": [],
        "schema": [],
        "mcp_endpoint": []
    }  # Dictionary mapping source types to lists of (item, score, ttl) tuples

    # Connection tests and notifications
    max_retries = 3
    grok_ok = False
    for attempt in range(1, max_retries + 1):
        if context.verbose_mode >= 1:
            click.echo(f"{Fore.YELLOW}Attempting to connect to Grok AI Endpoint (Attempt {attempt}/{max_retries}){Style.RESET_ALL}")
        try:
            grok_ok = test_connection(context.grok_config, 'Grok AI Endpoint', grok_headers, context.grok_config.get('endpoint', 'https://api.x.ai/v1'), grok_test_payload)
            if grok_ok:
                if context.verbose_mode >= 1:
                    click.echo(f"{Style.BRIGHT}Connected to Grok AI Endpoint{Style.RESET_ALL}")
                break
        except requests.exceptions.RequestException as e:
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Connection attempt {attempt} failed: {str(e)}{Style.RESET_ALL}")
            if attempt == max_retries:
                if context.verbose_mode >= 1:
                    click.echo(f"{Fore.RED}Failed to connect to Grok AI Endpoint after {max_retries} attempts{Style.RESET_ALL}")
                grok_ok = False
    mcp_ok = test_connection(context.mcp_config, 'MCP AI Endpoint "Little LLM"', mcp_headers, context.mcp_config.get('endpoint', ''))
    if mcp_ok and context.verbose_mode >= 1:
        click.echo(f"{Style.BRIGHT}Connected to MCP AI Endpoint \"Little LLM\"{Style.RESET_ALL}")
    elif context.verbose_mode >= 1:
        click.echo(f"{Fore.RED}MCP AI Endpoint connection failed. MCP calls will be skipped. Check 'mcp/mcp-service/endpoint' in config.json.{Style.RESET_ALL}")

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
        if not prompt:
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Empty input ignored. Please enter a valid query or command.{Style.RESET_ALL}")
            continue
        mcp_history.append_string(prompt)
        log_to_file(f"INPUT: {prompt}")
        
        if prompt == "/help":
            click.echo(f"{Style.BRIGHT}MCP Mode Commands:{Style.RESET_ALL}")
            click.echo("- /help: Shows this MCP mode-specific help.")
            click.echo("- /show-tokens: Displays the current token breakdown (system, history, KG context, total) and content (in verbose mode 2 or 3).")
            click.echo("- /reload-kg: Reloads the knowledge graph from the configured endpoint.")
            click.echo("- /back: Returns to the main CLI menu (or to MCP mode from test mode).")
            click.echo("- /exit: Exits the CLI entirely.")
            click.echo("- /mode:verbose 0/1/2/3: Sets verbosity (0=standard, 1=verbose, 2=extreme, 3=debug, currently {}).".format(context.verbose_mode))
            click.echo("- /mode:test: Enters a mode for sending requests to Grok-3 and MCP services.")
            click.echo("- Any other input: Sends the request to the MCP service (in test mode).")
        elif prompt == "/show-tokens":
            log_token_breakdown(context)
            log_token_content(context)
        elif prompt == "/reload-kg":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Reloading Knowledge Graph...{Style.RESET_ALL}")
            jsonld_graph = load_knowledge_graph(kg_url=context.kg_url, verbose_mode=context.verbose_mode)
            context.jsonld_graph = jsonld_graph  # Update context with new JSON-LD graph
            context.kg_context = ""  # Reset to empty
            context.context_matches_with_ttl["kg"] = []  # Reset KG matches on reload
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Knowledge Graph reloaded.{Style.RESET_ALL}")
        elif prompt == "/mode:verbose 0":
            context.verbose_mode = 0
            click.echo(f"{Style.BRIGHT}Verbose mode: Standard (0){Style.RESET_ALL}")
        elif prompt == "/mode:verbose 1":
            context.verbose_mode = 1
            click.echo(f"{Style.BRIGHT}Verbose mode: Verbose (1){Style.RESET_ALL}")
        elif prompt == "/mode:verbose 2":
            context.verbose_mode = 2
            click.echo(f"{Style.BRIGHT}Verbose mode: Extreme (2){Style.RESET_ALL}")
        elif prompt == "/mode:verbose 3":
            context.verbose_mode = 3
            click.echo(f"{Style.BRIGHT}Verbose mode: Debug (3){Style.RESET_ALL}")
        elif prompt == "/mode:test" and not in_test_mode:
            in_test_mode = True
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Now entering Test Mode. Requests will be sent to Grok-3 and MCP services.{Style.BRIGHT}")
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
                click.echo(f"{Fore.YELLOW}Usage log written to {context.log_file_path}{Style.RESET_ALL}")
            # Clean up old log files
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
        elif prompt == "/exit":
            if context.verbose_mode >= 1:
                click.echo(f"{Style.BRIGHT}Exiting CLI...{Style.RESET_ALL}")
                click.echo(f"{Fore.YELLOW}Usage log written to {context.log_file_path}{Style.RESET_ALL}")
            # Clean up old log files
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
            return True  # Signal exit to main CLI
        elif in_test_mode:
            try:
                # Process data sources and update matches with TTL
                result = process_data_sources(context, prompt)
                contexts = result["contexts"]
                matches_with_ttl = result["matches_with_ttl"]

                # Update context with new contexts
                context.kg_context = contexts["kg"]
                if not isinstance(context.kg_context, str):
                    if context.verbose_mode >= 1:
                        click.echo(f"{Fore.RED}Invalid KG context type: {type(context.kg_context)}{Style.RESET_ALL}")
                    context.kg_context = ""

                # Update context_matches_with_ttl with new matches
                context.context_matches_with_ttl.update(matches_with_ttl)
                if context.verbose_mode >= 2:
                    for source, matches in context.context_matches_with_ttl.items():
                        click.echo(f"{Fore.YELLOW}{source.capitalize()} context set to {len([m for m in matches if m[2] > 0])} active matches{Style.RESET_ALL}")

                # Fuzzy match prior messages
                history_matches = []
                fuzzy_scores = []
                try:
                    history_matches, fuzzy_scores = fuzzy_match_query(prompt, context.memory, key="content", verbose_mode=context.verbose_mode, fuzzy_threshold=context.fuzzy_threshold)
                    if not isinstance(history_matches, list):
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.RED}DEBUG: Invalid history_matches type: {type(history_matches)}{Style.RESET_ALL}")
                        history_matches = []
                        fuzzy_scores = []
                    if not isinstance(fuzzy_scores, list):
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.RED}DEBUG: Invalid fuzzy_scores type: {type(fuzzy_scores)}{Style.RESET_ALL}")
                        history_matches = []
                        fuzzy_scores = []
                except Exception as e:
                    if context.verbose_mode >= 2:
                        click.echo(f"{Fore.RED}DEBUG: Error in fuzzy_match_query for history: {str(e)}{Style.RESET_ALL}")
                    history_matches = []
                    fuzzy_scores = []
                if context.verbose_mode >= 3:
                    click.echo(f"{Fore.YELLOW}DEBUG: Raw history matches: {json.dumps(history_matches, indent=2)}{Style.RESET_ALL}")

                # Validate and filter history matches, limiting to conversation_history conversations
                valid_history_matches = []
                conversation_count = 0
                for i, item in enumerate(zip(history_matches, fuzzy_scores)):
                    if conversation_count >= context.conversation_history:  # Cap at conversation_history conversations
                        break
                    msg, score = item if isinstance(item, tuple) and len(item) == 2 else (None, None)
                    if isinstance(msg, dict) and "role" in msg and "content" in msg and isinstance(msg["content"], str):
                        valid_history_matches.append({"role": msg["role"], "content": msg["content"], "score": score})  # Store score for fuzzy matches
                        # Increment conversation count only for user messages to track conversations
                        if msg["role"] == "user":
                            conversation_count += 1
                    else:
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.RED}DEBUG: Invalid history match skipped: {msg} (Index: {i}){Style.RESET_ALL}")

                # Strip scores for payload to maintain original message structure
                valid_history_matches = [{"role": msg["role"], "content": msg["content"]} for msg in valid_history_matches]

                # Select recent messages, excluding those already in valid_history_matches
                recent_messages = []
                history_content_set = {msg["content"] for msg in valid_history_matches}
                remaining_conversations = context.conversation_history - conversation_count  # Cap at conversation_history conversations
                if remaining_conversations > 0:
                    for msg in reversed(context.memory):
                        if isinstance(msg, dict) and "role" in msg and "content" in msg and isinstance(msg["content"], str):
                            if msg["content"] not in history_content_set:
                                if "score" not in msg:  # Ensure score field for existing messages
                                    msg["score"] = 0.0
                                recent_messages.append({"role": msg["role"], "content": msg["content"]})
                                history_content_set.add(msg["content"])
                                # Increment conversation count for user messages
                                if msg["role"] == "user":
                                    conversation_count += 1
                                if conversation_count >= context.conversation_history:
                                    break

                # Combine history, ensuring total does not exceed 2 * conversation_history messages
                total_history = valid_history_matches + recent_messages
                if len(total_history) > 2 * context.conversation_history:
                    total_history = total_history[:2 * context.conversation_history]

                # Log memory summary in verbose mode
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}Conversation Memory prompts included (max {context.conversation_history} conversations, up to {2 * context.conversation_history} messages):{Style.RESET_ALL}")
                    if valid_history_matches:
                        click.echo(f"{Fore.YELLOW}  Fuzzy matched messages:{Style.RESET_ALL}")
                        for i, msg in enumerate(valid_history_matches):
                            content = msg["content"]
                            matched_word = content.lower().split()[0] if content else "<empty>"
                            before, after = get_context_words(content, matched_word)
                            role = msg["role"].capitalize()
                            click.echo(f"{Fore.YELLOW}    {role}: {before} **{matched_word}** {after} (Index: {i}){Style.RESET_ALL}")
                    if recent_messages:
                        click.echo(f"{Fore.YELLOW}  Recent messages (up to {remaining_conversations} conversations):{Style.RESET_ALL}")
                        for msg in recent_messages:
                            first_words = " ".join(msg["content"].split()[:5])
                            role = msg["role"].capitalize()
                            click.echo(f"{Fore.YELLOW}    {role}: {first_words}...{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}  Total messages included: {len(total_history)}/{2 * context.conversation_history}{Style.RESET_ALL}")

                # Construct messages
                try:
                    messages = [
                        {"role": "system", "content": f"{context.combined_system_prompt}\nKG context: {context.kg_context}" if context.kg_context else context.combined_system_prompt},
                    ] + total_history + [
                        {"role": "user", "content": prompt}
                    ]
                    if context.verbose_mode >= 3:
                        click.echo(f"{Fore.YELLOW}DEBUG: Raw messages before validation: {json.dumps(messages, indent=2)}{Style.RESET_ALL}")
                    # Validate messages
                    valid_messages = []
                    for msg in messages:
                        if isinstance(msg, dict) and "role" in msg and "content" in msg and isinstance(msg["content"], str):
                            valid_messages.append(msg)
                        else:
                            if context.verbose_mode >= 2:
                                click.echo(f"{Fore.RED}DEBUG: Invalid message format in payload: {msg}{Style.RESET_ALL}")
                    if not valid_messages:
                        if context.verbose_mode >= 1:
                            click.echo(f"{Fore.RED}No valid messages for Grok-3 request. Skipping API call.{Style.RESET_ALL}")
                        continue
                except Exception as e:
                    if context.verbose_mode >= 2:
                        click.echo(f"{Fore.RED}DEBUG: Error constructing messages: {str(e)}{Style.RESET_ALL}")
                    continue

                # Log tokens before Big LLM request
                log_token_breakdown(context, user_prompt=prompt)
                log_token_content(context, user_prompt=prompt)

                # Check token limit
                token_count = estimate_tokens(valid_messages)
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}Prompt token count: {token_count}{Style.RESET_ALL}")
                if token_count > context.token_limit:
                    # Truncate to system prompt, as many history messages as fit, and current prompt
                    remaining_slots = 2 * context.conversation_history  # Allow up to 2 * conversation_history messages
                    if len(total_history) > remaining_slots:
                        total_history = total_history[:remaining_slots]
                    valid_messages = [valid_messages[0]] + total_history[:remaining_slots] + [valid_messages[-1]]
                    if context.verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Truncated prompt to {estimate_tokens(valid_messages)} tokens{Style.RESET_ALL}")

                if grok_ok:
                    try:
                        payload = {
                            "model": context.grok_config.get('model', 'grok-3'),
                            "messages": valid_messages
                        }
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.YELLOW}DEBUG: Grok-3 payload: {json.dumps(payload, indent=2)}{Style.RESET_ALL}")
                        response = session.post(context.grok_config.get('endpoint'), json=payload, headers=grok_headers, timeout=10)
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.YELLOW}DEBUG: Grok-3 raw response: {response.text} (Status: {response.status_code}){Style.RESET_ALL}")
                        response.raise_for_status()
                        try:
                            response_json = response.json()
                            if isinstance(response_json, str):
                                if context.verbose_mode >= 3:
                                    click.echo(f"{Fore.RED}DEBUG: Grok-3 response is a string, not JSON: {response_json} (Status: {response.status_code}){Style.RESET_ALL}")
                                content = f"No valid JSON response: {response_json}"
                            else:
                                content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "No response")
                        except json.JSONDecodeError as e:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.RED}DEBUG: Invalid JSON from Grok-3: {response.text} (Status: {response.status_code}, Error: {str(e)}){Style.RESET_ALL}")
                            content = f"No valid JSON response: {response.text}"
                        except Exception as e:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.RED}DEBUG: Error processing Grok-3 response: {str(e)} (Raw: {response.text}, Status: {response.status_code}){Style.RESET_ALL}")
                            content = f"Error processing Grok-3 response: {str(e)}"
                    except Exception as e:
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.RED}DEBUG: Grok-3 request failed: {str(e)} (Status: {response.status_code if 'response' in locals() else 'N/A'}, Payload: {json.dumps(payload, indent=2) if 'payload' in locals() else 'Not constructed'}){Style.RESET_ALL}")
                        content = f"Grok API request failed: {str(e)}"
                    if context.verbose_mode >= 3:
                        click.echo(f"{Fore.YELLOW}DEBUG: Grok-3 response content: {content}{Style.RESET_ALL}")
                    click.echo(f"{Style.BRIGHT}> (Grok Response:) {content}{Style.RESET_ALL}")

                    # Store user prompt and response with default score
                    context.memory.append({"role": "user", "content": prompt, "timestamp": datetime.now().isoformat(), "score": 0.0})
                    context.memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat(), "score": 0.0})
                    # Preserve last 100 messages
                    if len(context.memory) > 100:
                        context.memory = context.memory[-100:]
                    log_token_breakdown(context)
                    log_token_content(context)

                if mcp_ok:
                    try:
                        # Parse Grok-3 response as JSON
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.YELLOW}DEBUG: Attempting to parse Grok-3 response as JSON: {content}{Style.RESET_ALL}")
                        mcp_payload = json.loads(content)
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}MCP request: {json.dumps(mcp_payload, indent=2)}{Style.RESET_ALL}")
                        response = session.post(context.mcp_config.get('endpoint'), json=mcp_payload, headers=mcp_headers, timeout=10)
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.YELLOW}DEBUG: MCP raw response: {response.text} (Status: {response.status_code}){Style.RESET_ALL}")
                        response.raise_for_status()
                        try:
                            response_json = response.json()
                            content = response_json.get("result", "No response")
                        except json.JSONDecodeError:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.YELLOW}DEBUG: MCP response is not valid JSON: {response.text} (Status: {response.status_code}){Style.RESET_ALL}")
                            content = response.text
                        except Exception as e:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.RED}DEBUG: Error processing MCP response: {str(e)} (Raw: {response.text}, Status: {response.status_code}){Style.RESET_ALL}")
                            content = f"Error processing MCP response: {str(e)}"
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}MCP response: {content}{Style.RESET_ALL}")
                        click.echo(f"{Style.BRIGHT}> (MCP Response:) {content}{Style.RESET_ALL}")
                    except json.JSONDecodeError:
                        if context.verbose_mode >= 1:
                            click.echo(f"{Fore.RED}Invalid JSON from Grok-3: {content}. Falling back to original query.{Style.RESET_ALL}")
                        mcp_payload = {"query": prompt}
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}MCP request: {json.dumps(mcp_payload, indent=2)}{Style.RESET_ALL}")
                        response = session.post(context.mcp_config.get('endpoint'), json=mcp_payload, headers=mcp_headers, timeout=10)
                        if context.verbose_mode >= 3:
                            click.echo(f"{Fore.YELLOW}DEBUG: MCP raw response: {response.text} (Status: {response.status_code}){Style.RESET_ALL}")
                        response.raise_for_status()
                        try:
                            response_json = response.json()
                            content = response_json.get("result", "No response")
                        except json.JSONDecodeError:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.YELLOW}DEBUG: MCP response is not valid JSON: {response.text} (Status: {response.status_code}){Style.RESET_ALL}")
                            content = response.text
                        except Exception as e:
                            if context.verbose_mode >= 3:
                                click.echo(f"{Fore.RED}DEBUG: Error processing MCP response: {str(e)} (Raw: {response.text}, Status: {response.status_code}){Style.RESET_ALL}")
                            content = f"Error processing MCP response: {str(e)}"
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}MCP response: {content}{Style.RESET_ALL}")
                        click.echo(f"{Style.BRIGHT}> (MCP Response:) {content}{Style.RESET_ALL}")

                    # Store MCP response with default score
                    context.memory.append({"role": "assistant", "content": content, "timestamp": datetime.now().isoformat(), "score": 0.0})
                    # Preserve last 100 messages
                    if len(context.memory) > 100:
                        context.memory = context.memory[-100:]
                    log_token_breakdown(context)
                    log_token_content(context)

                # Update TTLs for all data source matches after request/response cycle
                for source, matches in context.context_matches_with_ttl.items():
                    expired_matches = []
                    for match in matches:
                        match[2] -= 1  # Decrement TTL
                        if match[2] <= 0:
                            expired_matches.append(match)
                    for expired in expired_matches:
                        matches.remove(expired)
                        if context.verbose_mode >= 2:
                            click.echo(f"{Fore.YELLOW}Removed expired {source} match (TTL 0): {json.dumps(expired[0], sort_keys=True)[:50]}...{Style.RESET_ALL}")
                    if context.verbose_mode >= 2:
                        ttl_range = f"{min([m[2] for m in matches], default=0)}-{max([m[2] for m in matches], default=0)}" if matches else "0-0"
                        click.echo(f"{Fore.YELLOW}{source.capitalize()} matches after TTL update: {len(matches)} (TTL range: {ttl_range}){Style.RESET_ALL}")

            except Exception as e:
                if context.verbose_mode >= 2:
                    click.echo(f"{Fore.RED}API error details: {e}\nPayload: {json.dumps(payload, indent=2) if 'payload' in locals() else 'Not constructed'}{Style.RESET_ALL}")
                click.echo(f"{Fore.RED}Error communicating with API: {e}{Style.RESET_ALL}")
        else:
            if context.verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Input ignored in MCP mode. Enter /mode:test to send requests.{Style.RESET_ALL}")
