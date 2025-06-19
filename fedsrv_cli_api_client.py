import requests
import click
from colorama import Fore, Style

def test_connection(config, name, headers, endpoint, test_payload=None):
    """Test connection to an API endpoint."""
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