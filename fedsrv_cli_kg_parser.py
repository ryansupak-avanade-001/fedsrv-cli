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
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                if verbose_mode:
                    click.echo(f"{Fore.YELLOW}Attempting to connect to {kg_endpoint} (Attempt {attempt}/{max_retries}){Style.RESET_ALL}")
                try:
                    response = requests.get(kg_endpoint, timeout=10)
                    response.raise_for_status()
                    raw_content = response.content
                    break
                except requests.exceptions.RequestException as e:
                    if verbose_mode:
                        click.echo(f"{Fore.YELLOW}Connection attempt {attempt} failed: {str(e)}{Style.RESET_ALL}")
                    if attempt == max_retries:
                        click.echo(f"{Fore.RED}Failed to connect to {kg_endpoint} after {max_retries} attempts{Style.RESET_ALL}")
                        return jsonld_graph
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
                subclass_count = 0
                object_property_count = 0
                object_property_domain_count = 0

                # Parse Classes
                for cls in root.findall('Declaration/Class', ns):
                    iri = cls.get('abbreviatedIRI')
                    if iri:
                        class_count += 1
                        jsonld_graph["@graph"].append({
                            "@id": iri,
                            "@type": "Class"
                        })

                # Parse SubClassOf relationships
                for subclass_of in root.findall('SubClassOf', ns):
                    classes = subclass_of.findall('Class', ns)
                    if len(classes) == 2:
                        subclass_iri = classes[0].get('abbreviatedIRI')
                        superclass_iri = classes[1].get('abbreviatedIRI')
                        if subclass_iri and superclass_iri:
                            subclass_count += 1
                            # Find or create the subclass entry
                            subclass_entry = next((item for item in jsonld_graph["@graph"] if item["@id"] == subclass_iri), None)
                            if not subclass_entry:
                                jsonld_graph["@graph"].append({
                                    "@id": subclass_iri,
                                    "@type": "Class",
                                    "rdfs:subClassOf": {"@id": superclass_iri}
                                })
                            else:
                                subclass_entry["rdfs:subClassOf"] = {"@id": superclass_iri}

                # Parse Object Properties
                for obj_prop in root.findall('Declaration/ObjectProperty', ns):
                    iri = obj_prop.get('abbreviatedIRI')
                    if iri:
                        object_property_count += 1
                        jsonld_graph["@graph"].append({
                            "@id": iri,
                            "@type": "ObjectProperty"
                        })

                # Parse Object Property Domains
                for obj_prop_domain in root.findall('ObjectPropertyDomain', ns):
                    obj_prop = obj_prop_domain.find('ObjectProperty', ns)
                    cls = obj_prop_domain.find('Class', ns)
                    if obj_prop is not None and cls is not None:
                        prop_iri = obj_prop.get('abbreviatedIRI')
                        class_iri = cls.get('abbreviatedIRI')
                        if prop_iri and class_iri:
                            object_property_domain_count += 1
                            # Find or create the object property entry
                            prop_entry = next((item for item in jsonld_graph["@graph"] if item["@id"] == prop_iri and item["@type"] == "ObjectProperty"), None)
                            if not prop_entry:
                                jsonld_graph["@graph"].append({
                                    "@id": prop_iri,
                                    "@type": "ObjectProperty",
                                    "rdfs:domain": {"@id": class_iri}
                                })
                            else:
                                prop_entry["rdfs:domain"] = {"@id": class_iri}

                if verbose_mode:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subclass_count} subclasses to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_count} standalone object properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_domain_count} object property domains to JSON-LD{Style.RESET_ALL}")
                return jsonld_graph
            except ET.ParseError as e:
                click.echo(f"{Fore.RED}Failed to parse XML: {e}{Style.RESET_ALL}")
                return jsonld_graph
        elif kg_endpoint.lower().endswith('.jsonld'):
            try:
                click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as JSON-LD from {kg_endpoint}{Style.RESET_ALL}")
                json_data = json.loads(kg_content)
                class_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'Class')
                subclass_count = sum(1 for item in json_data.get('@graph', []) if item.get('rdfs:subClassOf'))
                object_property_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'ObjectProperty' and 'rdfs:domain' not in item)
                object_property_domain_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'ObjectProperty' and 'rdfs:domain' in item)
                if verbose_mode:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subclass_count} subclasses to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_count} standalone object properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_domain_count} object property domains to JSON-LD{Style.RESET_ALL}")
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
