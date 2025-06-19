import requests
import xml.etree.ElementTree as ET
import xml.sax
import chardet
import json
import os
import click
from colorama import Fore, Style

def validate_xml(content):
    """Validate XML content for well-formedness."""
    try:
        xml.sax.parseString(content, xml.sax.handler.ContentHandler())
        return True, ""
    except xml.sax.SAXParseException as e:
        return False, str(e)

def load_knowledge_graph(startup_prompts, verbose_mode=False):
    """Load Knowledge Graph from startup-prompts where name='get-kg'."""
    kg_endpoint = None
    for prompt in startup_prompts:
        if prompt.get("name") == "get-kg" and "content" in prompt:
            kg_endpoint = prompt["content"]
            break

    if not kg_endpoint:
        click.echo(f"{Fore.YELLOW}No get-kg endpoint found in startup-prompts{Style.RESET_ALL}")
        return {"@graph": []}

    jsonld_graph = {"@graph": []}
    max_file_size = 50 * 1024 * 1024  # 50MB limit
    content_lines = None
    raw_content = None

    try:
        if kg_endpoint.startswith(("http://", "https://")):
            response = requests.get(kg_endpoint, timeout=10)
            response.raise_for_status()
            raw_content = response.content
            encoding_info = chardet.detect(raw_content)
            encoding = encoding_info['encoding'] or 'utf-8'
            kg_content = raw_content.decode(encoding)
            content_lines = kg_content.splitlines()
            if not content_lines or all(line.strip() == '' for line in content_lines):
                click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                return jsonld_graph
        elif kg_endpoint.startswith("file://"):
            local_path = kg_endpoint.replace("file://", "")
            if not os.path.exists(local_path):
                click.echo(f"{Fore.YELLOW}KG file {local_path} does not exist{Style.RESET_ALL}")
                return jsonld_graph
            if os.path.getsize(local_path) > max_file_size:
                click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return jsonld_graph
            with open(local_path, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return jsonld_graph
        elif os.path.exists(kg_endpoint):
            if os.path.getsize(kg_endpoint) > max_file_size:
                click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return jsonld_graph
            with open(kg_endpoint, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return jsonld_graph
        else:
            click.echo(f"{Fore.YELLOW}KG endpoint {kg_endpoint} is neither a valid URL nor local file{Style.RESET_ALL}")
            return jsonld_graph

        if kg_endpoint.lower().endswith(('.owx', '.owl', '.xml')):
            is_valid, xml_error = validate_xml(kg_content)
            if not is_valid:
                click.echo(f"{Fore.YELLOW}Invalid XML: {xml_error}{Style.RESET_ALL}")
            try:
                click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as generic XML from {kg_endpoint}{Style.RESET_ALL}")
                root = ET.fromstring(kg_content)
                ns = {'': 'http://www.w3.org/2002/07/owl#'}
                class_count = 0
                for cls in root.findall('Declaration/Class', ns):
                    iri = cls.get('abbreviatedIRI')
                    if iri:
                        class_count += 1
                        jsonld_graph["@graph"].append({
                            "@id": iri,
                            "@type": "Class"
                        })
                if verbose_mode:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                return jsonld_graph
            except ET.ParseError as e:
                click.echo(f"{Fore.RED}Failed to parse XML: {e}{Style.RESET_ALL}")
                return jsonld_graph
        elif kg_endpoint.lower().endswith('.jsonld'):
            try:
                click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as JSON-LD from {kg_endpoint}{Style.RESET_ALL}")
                json_data = json.loads(kg_content)
                class_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'Class')
                if verbose_mode:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                return json_data
            except json.JSONDecodeError as e:
                click.echo(f"{Fore.RED}Failed to parse JSON-LD: {e}{Style.RESET_ALL}")
                return jsonld_graph
        else:
            click.echo(f"{Fore.YELLOW}Unsupported file format for {kg_endpoint}{Style.RESET_ALL}")
            return jsonld_graph

    except Exception as e:
        click.echo(f"{Fore.RED}Unexpected error: {str(e)}{Style.RESET_ALL}")
        return jsonld_graph
