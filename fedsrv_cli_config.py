#fedsrv_cli_config.py
#0bee5d0a-ef86-4368-afd6-02cac7d49116
import os
import json
from dotenv import load_dotenv
import click
from colorama import Fore, Style

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
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    load_dotenv()
    config_json = os.getenv("CONFIG_JSON")
    if config_json:
        try:
            config = json.loads(config_json)
        except json.JSONDecodeError as e:
            click.echo(f"{Fore.RED}Error parsing CONFIG_JSON from .env: {e}{Style.RESET_ALL}")
            raise click.Abort()

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                json_config = json.load(f)
                config = merge_dicts(json_config, config)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            click.echo(f"{Fore.RED}Error loading config.json: {e}{Style.RESET_ALL}")
            raise click.Abort()

    if not config:
        click.echo(f"{Fore.RED}No configuration found: .env with CONFIG_JSON or config.json required{Style.RESET_ALL}")
        raise click.Abort()

    # Set default log-history if not specified
    config.setdefault("cli", {}).setdefault("log-history", 10)
    return config
