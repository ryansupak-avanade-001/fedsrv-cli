#fedsrv_cli_fuzzy_matcher.py
#c7d8e9f0-3a4b-4c8a-9e7b-6f5c8d0c9e2a
from rapidfuzz import fuzz
import click
from colorama import Fore, Style

def fuzzy_match_query(query, items, key=None, verbose_mode=False, fuzzy_threshold=70):
    """Fuzzy match query against a list of items (KG labels or messages)."""
    matches = []
    query = query.lower()
    for item in items:
        text = item.lower() if key is None else item[key].lower()
        score = fuzz.token_sort_ratio(query, text)
        if score > fuzzy_threshold:
            matches.append((item, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    matched_items = [m[0] for m in matches]  # Return all matches
    if verbose_mode:
        display_items = [(m[0][key] if key and isinstance(m[0], dict) else m[0], m[1]) for m in matches[:5]]  # Log up to 5 for display
        click.echo(f"{Fore.YELLOW}Fuzzy matches (score > {fuzzy_threshold}): {display_items}{Style.RESET_ALL}")
    return matched_items, matches  # Return all matches and scores

def get_context_words(text, matched_word, before=3, after=3):
    """Extract words before and after a matched word."""
    words = text.split()
    for i, word in enumerate(words):
        if word.lower() == matched_word.lower():
            start = max(0, i - before)
            end = min(len(words), i + after + 1)
            before_words = " ".join(words[start:i])
            after_words = " ".join(words[i+1:end])
            return before_words, after_words
    return "", ""
