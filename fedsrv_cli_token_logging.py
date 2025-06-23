from dataclasses import dataclass
from typing import List, Optional
from colorama import Fore, Style
import click
from fedsrv_cli_utils import estimate_tokens

def log_token_breakdown(context: 'CliContext', user_prompt: Optional[str] = None) -> None:
    """Log token breakdown for Verbose Mode 1+."""
    if context.verbose_mode < 1:
        return
    system_tokens = estimate_tokens([{"role": "system", "content": context.combined_system_prompt}])
    history_tokens = estimate_tokens(context.memory)
    kg_tokens = estimate_tokens([{"content": context.kg_context}]) if context.kg_context else 0
    user_tokens = estimate_tokens([{"role": "user", "content": user_prompt}]) if user_prompt else 0
    total_tokens = system_tokens + history_tokens + kg_tokens + user_tokens
    prefix = "Token breakdown" + (" for Big LLM request" if user_prompt else "")
    click.echo(f"{Fore.YELLOW}{prefix}:{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  System tokens: {system_tokens}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  History tokens: {history_tokens}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  KG context tokens: {kg_tokens}{Style.RESET_ALL}")
    if user_prompt:
        click.echo(f"{Fore.YELLOW}  User prompt tokens: {user_tokens}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  Total tokens: {total_tokens}/{context.token_limit}{Style.RESET_ALL}")

def log_token_content(context: 'CliContext', user_prompt: Optional[str] = None) -> None:
    """Log exact token content for Verbose Mode 2+."""
    if context.verbose_mode < 2:
        return
    system_prompt_content = context.combined_system_prompt or "<No System Prompt>"
    kg_context_content = context.kg_context or "<No KG Matches>"
    memory_content = context.memory or ["<No Conversation Memory>"]
    prefix = "Exact token content" + (" for Big LLM request" if user_prompt else "")
    click.echo(f"{Fore.YELLOW}{prefix}:{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  System prompt: {system_prompt_content}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  KG context: {kg_context_content}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}  Conversation Memory:{Style.RESET_ALL}")
    if memory_content == ["<No Conversation Memory>"]:
        click.echo(f"{Fore.YELLOW}    <No Conversation Memory>{Style.RESET_ALL}")
    else:
        for msg in memory_content:
            click.echo(f"{Fore.YELLOW}    {msg['role'].capitalize()}: {msg['content'][:50]}...{Style.RESET_ALL}")
    if user_prompt:
        click.echo(f"{Fore.YELLOW}  User prompt: {user_prompt}{Style.RESET_ALL}")
