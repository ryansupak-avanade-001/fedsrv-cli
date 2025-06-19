import requests
import xml.etree.ElementTree as ET
import xml.sax
import chardet
import json
import click
from colorama import Fore, Style

def validate_xml(content):
    """Validate XML content for well-formedness."""
    try:
        xml.sax.parseString(content, xml.sax.handler.ContentHandler())
        return True, ""
    except xml.sax.SAXParseException as e:
        return False, str(e)

def load_knowledge_graph(startup_prompts):
    """Load Knowledge Graph from startup-prompts where name='get-kg'."""
    kg_endpoint = None
    for prompt in startup_prompts:
        if prompt.get("name") == "get-kg" and "content" in prompt:
            kg_endpoint = prompt["content"]
            break

    if not kg_endpoint:
        click.echo(f"{Fore.YELLOW}No get-kg endpoint found in startup-prompts{Style.RESET_ALL}")
        return []

    kg_labels = []
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
                return []
        elif kg_endpoint.startswith("file://"):
            local_path = kg_endpoint.replace("file://", "")
            if not os.path.exists(local_path):
                click.echo(f"{Fore.YELLOW}KG file {local_path} does not exist{Style.RESET_ALL}")
                return []
            if os.path.getsize(local_path) > max_file_size:
                click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return []
            with open(local_path, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return []
        elif os.path.exists(kg_endpoint):
            if os.path.getsize(kg_endpoint) > max_file_size:
                click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return []
            with open(kg_endpoint, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return []
        else:
            click.echo(f"{Fore.YELLOW}KG endpoint {kg_endpoint} is neither a valid URL nor local file{Style.RESET_ALL}")
            return []

        if kg_endpoint.lower().endswith(('.owx', '.owl', '.xml')):
            is_valid, xml_error = validate_xml(kg_content)
            if not is_valid:
                click.echo(f"{Fore.YELLOW}Invalid XML: {xml_error}{Style.RESET_ALL}")
            try:
                root = ET.fromstring(kg_content)
                ns = {'owl': 'http://www.w3.org/2002/07/owl#', 'rdfs': 'http://www.w3.org/2000/01/rdf-schema#'}
                for cls in root.findall('.//owl:Class', ns):
                    iri = cls.get('IRI')
                    if iri:
                        kg_labels.append(iri.split('#')[-1].split('/')[-1])
                for ann in root.findall('.//owl:AnnotationAssertion', ns):
                    literal = ann.find('.//rdfs:Literal', ns)
                    if literal is not None and literal.text:
                        kg_labels.append(literal.text)
                for ann in root.findall('.//owl:Annotation', ns):
                    literal = ann.find('.//rdfs:Literal', ns)
                    if literal is not None and literal.text:
                        kg_labels.append(literal.text)
                click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as generic XML from {kg_endpoint}{Style.RESET_ALL}")
                return kg_labels
            except ET.ParseError as e:
                click.echo(f"{Fore.RED}Failed to parse XML: {e}{Style.RESET_ALL}")
                return []
        elif kg_endpoint.lower().endswith('.jsonld'):
            try:
                json_data = json.loads(kg_content)
                for item in json_data.get('@graph', []):
                    if 'rdfs:label' in item:
                        label = item['rdfs:label']
                        kg_labels.append(label if isinstance(label, str) else label.get('@value', ''))
                    if 'rdfs:comment' in item:
                        comment = item['rdfs:comment']
                        kg_labels.append(comment if isinstance(comment, str) else comment.get('@value', ''))
                    if '@id' in item:
                        kg_labels.append(item['@id'].split('#')[-1].split('/')[-1])
                click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as JSON-LD from {kg_endpoint}{Style.RESET_ALL}")
                return kg_labels
            except json.JSONDecodeError as e:
                click.echo(f"{Fore.RED}Failed to parse JSON-LD: {e}{Style.RESET_ALL}")
                return []
        else:
            click.echo(f"{Fore.YELLOW}Unsupported file format for {kg_endpoint}{Style.RESET_ALL}")
            return []

    except Exception as e:
        click.echo(f"{Fore.RED}Unexpected error: {str(e)}{Style.RESET_ALL}")
        return []