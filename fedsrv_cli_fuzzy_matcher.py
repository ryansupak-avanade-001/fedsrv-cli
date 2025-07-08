#fedsrv_cli_fuzzy_matcher.py
#fuzzy_matcher_artifact
from typing import List, Tuple
from rapidfuzz import fuzz
from colorama import Fore, Style
import click

def fuzzy_match_query(query: str, items: List[str], verbose_mode: int = 0, fuzzy_threshold: float = 70, key: str = None) -> Tuple[List[dict], List[Tuple[str, float]]]:
    """Fuzzy match a query against a list of items, returning matched items and their scores."""
    matches = []
    fuzzy_scores = []
    for i, item in enumerate(items):
        content = item[key] if key and isinstance(item, dict) else item
        score = fuzz.partial_ratio(query.lower(), content.lower())
        if score >= fuzzy_threshold:
            matches.append(item)
            fuzzy_scores.append((content, score))
    if verbose_mode >= 2 and key != "content":  # Suppress logging for history matching
        click.echo(f"{Fore.YELLOW}Fuzzy matches (score > {fuzzy_threshold}): {fuzzy_scores}{Style.RESET_ALL}")
    return matches, fuzzy_scores

def get_context_words(content: str, matched_word: str) -> Tuple[str, str]:
    """Extract words before and after a matched word for context."""
    words = content.lower().split()
    try:
        idx = words.index(matched_word.lower())
        before = " ".join(words[max(0, idx - 2):idx])
        after = " ".join(words[idx + 1:idx + 3])
        return before, after
    except ValueError:
        return "", ""
