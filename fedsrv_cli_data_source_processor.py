#fedsrv_cli_data_source_processor.py
#a7b3e9f2-4c1d-4e6a-8f9b-2d3c5e7a9b1c
import json
import re
import click
from colorama import Fore, Style
from fedsrv_cli_fuzzy_matcher import fuzzy_match_query

# Knowledge Graph Processing
def extract_kg_items(jsonld_graph):
    """Extract values and items from jsonld_graph for fuzzy matching."""
    items = []
    for idx, item in enumerate(jsonld_graph.get('@graph', [])):
        for key, value in item.items():
            if key != '@type':
                if isinstance(value, str):
                    items.append((value, item, idx))
                elif isinstance(value, dict) and '@id' in value:
                    items.append((value['@id'], item, idx))
                elif isinstance(value, list):
                    for subitem in value:
                        if isinstance(subitem, dict) and '@id' in subitem:
                            items.append((subitem['@id'], item, idx))
    return items

def deduplicate_matches(matches):
    """Deduplicate KG matches by JSON equality, keeping highest score."""
    match_dict = {}
    for item, score, idx in matches:
        item_json = json.dumps(item, sort_keys=True)
        if item_json not in match_dict or score > match_dict[item_json][1]:
            match_dict[item_json] = (item, score)
    return [item for item, _ in match_dict.values()]

def process_kg_source(query, jsonld_graph, verbose_mode, fuzzy_threshold):
    """Process query against knowledge graph, return context string."""
    # Split prompt into words, stripping non-alphanumeric characters
    words = [re.sub(r'[^a-zA-Z0-9]', '', word.lower()) for word in query.split() if re.sub(r'[^a-zA-Z0-9]', '', word)]
    words = list(dict.fromkeys(words))  # Deduplicate words
    if verbose_mode >= 2:
        click.echo(f"{Fore.YELLOW}Query words for fuzzy search: {words}{Style.RESET_ALL}")

    # Fuzzy match each word
    all_matches = []
    kg_items = extract_kg_items(jsonld_graph)
    try:
        for word in words:
            matches, fuzzy_scores = fuzzy_match_query(word, [item[0] for item in kg_items], verbose_mode=verbose_mode, fuzzy_threshold=fuzzy_threshold)
            if not isinstance(fuzzy_scores, list):
                if verbose_mode >= 2:
                    click.echo(f"{Fore.RED}DEBUG: Invalid fuzzy_scores type: {type(fuzzy_scores)}{Style.RESET_ALL}")
                continue
            for i, score_item in enumerate(fuzzy_scores):
                if not isinstance(score_item, tuple) or len(score_item) != 2:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.RED}DEBUG: Invalid fuzzy_scores item at index {i}: {score_item}{Style.RESET_ALL}")
                    continue
                value, score = score_item
                for j, item in enumerate(kg_items):
                    if item[0] == value and j not in [m[2] for m in all_matches]:
                        all_matches.append((item[1], score, j))
                        break
    except Exception as e:
        if verbose_mode >= 2:
            click.echo(f"{Fore.RED}DEBUG: Error in fuzzy matching: {str(e)}{Style.RESET_ALL}")
        all_matches = []

    # Log pre-deduplication matches in Debug mode
    if verbose_mode >= 3:
        click.echo(f"{Fore.YELLOW}DEBUG: Fuzzy matches before deduplication: {len(all_matches)}{Style.RESET_ALL}")
        for item, score, idx in all_matches:
            click.echo(f"{Fore.YELLOW}DEBUG: Pre-deduplication match (index {idx}): {json.dumps(item, indent=2)} (Score: {score:.1f}){Style.RESET_ALL}")

    # Deduplicate matches
    matched_elements = deduplicate_matches(all_matches)

    # Log post-deduplication count in Debug mode
    if verbose_mode >= 3:
        click.echo(f"{Fore.YELLOW}DEBUG: Fuzzy matches after deduplication: {len(matched_elements)}{Style.RESET_ALL}")

    # Set kg_context to matched elements as JSON
    try:
        kg_context = json.dumps(matched_elements) if matched_elements else ""
    except Exception as e:
        if verbose_mode >= 2:
            click.echo(f"{Fore.RED}DEBUG: Error serializing kg_context: {str(e)}{Style.RESET_ALL}")
        kg_context = ""
    if verbose_mode >= 3:
        click.echo(f"{Fore.YELLOW}DEBUG: KG context set to: {kg_context}{Style.RESET_ALL}")

    # Log matches in verbose mode
    if verbose_mode >= 1:
        click.echo(f"{Fore.YELLOW}Total fuzzy matches: {len(matched_elements)}{Style.RESET_ALL}")
    if verbose_mode >= 2:
        click.echo(f"{Fore.YELLOW}Fuzzy matched KG elements: {len(matched_elements)}{Style.RESET_ALL}")
        for item in matched_elements:
            score = next((s for i, s, idx in all_matches if json.dumps(i, sort_keys=True) == json.dumps(item, sort_keys=True)), 0)
            click.echo(f"{Fore.YELLOW}  {json.dumps(item, indent=2)} (Score: {score:.1f}){Style.RESET_ALL}")

    return kg_context

# Placeholder for Other Sources
def process_schema_source(query, schema_data, verbose_mode, threshold):
    """Placeholder for schema file processing."""
    return ""  # Return empty context until implemented

def process_mcp_endpoint_source(query, endpoints, verbose_mode, threshold):
    """Placeholder for MCP endpoint processing."""
    return ""  # Return empty context until implemented

# Top-Level Processor
def process_data_sources(context, query):
    """Process all data sources and return combined context."""
    kg_context = process_kg_source(query, context.jsonld_graph, context.verbose_mode, context.fuzzy_threshold)
    schema_context = process_schema_source(query, None, context.verbose_mode, context.fuzzy_threshold)
    mcp_context = process_mcp_endpoint_source(query, None, context.verbose_mode, context.fuzzy_threshold)
    return {"kg": kg_context, "schema": schema_context, "mcp_endpoint": mcp_context}
