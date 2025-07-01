import requests
import xml.etree.ElementTree as ET
import xml.sax
import chardet
import json
import os
import click
from colorama import Fore, Style
from fedsrv_cli_config import load_config

def validate_xml(content):
    """Validate XML content for well-formedness."""
    try:
        xml.sax.parseString(content, xml.sax.handler.ContentHandler())
        return True, ""
    except xml.sax.SAXParseException as e:
        return False, str(e)

def load_knowledge_graph(kg_url: str = None, verbose_mode: int = 0) -> dict:
    """Load Knowledge Graph from a URL or file specified in kg_url."""
    config = load_config()
    cli_config = config["mcp"].get("cli", {})
    xml_search_paths = cli_config.get("xml_search_paths", {})
    class_paths = xml_search_paths.get("class_paths", ["Declaration/Class"])
    subclass_paths = xml_search_paths.get("subclass_paths", ["SubClassOf"])
    object_property_paths = xml_search_paths.get("object_property_paths", ["Declaration/ObjectProperty"])
    object_property_domain_paths = xml_search_paths.get("object_property_domain_paths", ["ObjectPropertyDomain"])
    annotation_paths = xml_search_paths.get("annotation_paths", ["Annotation"])
    subobject_property_paths = xml_search_paths.get("subobject_property_paths", ["SubObjectPropertyOf"])
    annotation_assertion_paths = xml_search_paths.get("annotation_assertion_paths", ["AnnotationAssertion"])
    object_min_cardinality_paths = xml_search_paths.get("object_min_cardinality_paths", ["SubClassOf"])
    object_union_paths = xml_search_paths.get("object_union_paths", ["ObjectPropertyDomain/ObjectUnionOf"])

    if not kg_url:
        if verbose_mode >= 1:
            click.echo(f"{Fore.YELLOW}No KG URL found in configuration{Style.RESET_ALL}")
        return {"@graph": []}

    jsonld_graph = {"@graph": []}
    max_file_size = 50 * 1024 * 1024  # 50MB limit
    content_lines = None
    raw_content = None

    try:
        if kg_url.startswith(("http://", "https://")):
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                if verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}Attempting to connect to {kg_url} (Attempt {attempt}/{max_retries}){Style.RESET_ALL}")
                try:
                    response = requests.get(kg_url, timeout=10)
                    response.raise_for_status()
                    raw_content = response.content
                    break
                except requests.exceptions.RequestException as e:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Connection attempt {attempt} failed: {str(e)}{Style.RESET_ALL}")
                    if attempt == max_retries:
                        if verbose_mode >= 1:
                            click.echo(f"{Fore.RED}Failed to connect to {kg_url} after {max_retries} attempts{Style.RESET_ALL}")
                        return jsonld_graph
            encoding_info = chardet.detect(raw_content)
            encoding = encoding_info['encoding'] or 'utf-8'
            kg_content = raw_content.decode(encoding)
            content_lines = kg_content.splitlines()
            if not content_lines or all(line.strip() == '' for line in content_lines):
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                return jsonld_graph
        elif kg_url.startswith("file://"):
            local_path = kg_url.replace("file://", "")
            if not os.path.exists(local_path):
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}KG file {local_path} does not exist{Style.RESET_ALL}")
                return jsonld_graph
            if os.path.getsize(local_path) > max_file_size:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return jsonld_graph
            with open(local_path, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    if verbose_mode >= 1:
                        click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return jsonld_graph
        elif os.path.exists(kg_url):
            if os.path.getsize(kg_url) > max_file_size:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}KG file exceeds size limit ({max_file_size / 1024 / 1024}MB){Style.RESET_ALL}")
                return jsonld_graph
            with open(kg_url, 'rb') as f:
                raw_content = f.read()
                encoding_info = chardet.detect(raw_content)
                encoding = encoding_info['encoding'] or 'utf-8'
                kg_content = raw_content.decode(encoding)
                content_lines = kg_content.splitlines()
                if not content_lines or all(line.strip() == '' for line in content_lines):
                    if verbose_mode >= 1:
                        click.echo(f"{Fore.YELLOW}KG file is empty or invalid{Style.RESET_ALL}")
                    return jsonld_graph
        else:
            if verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}KG endpoint {kg_url} is neither a valid URL nor local file{Style.RESET_ALL}")
            return jsonld_graph

        if kg_url.lower().endswith(('.owx', '.owl', '.xml')):
            is_valid, xml_error = validate_xml(kg_content)
            if not is_valid:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Invalid XML: {xml_error}{Style.RESET_ALL}")
                return jsonld_graph
            try:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as generic XML from {kg_url}{Style.RESET_ALL}")
                if verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}XML content (first 10 lines): {content_lines[:10]}{Style.RESET_ALL}")
                root = ET.fromstring(kg_content)
                if verbose_mode >= 2:
                    click.echo(f"{Fore.YELLOW}XML root tag: {root.tag}{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}XML root attributes: {root.attrib}{Style.RESET_ALL}")
                ns = {'': 'http://www.w3.org/2002/07/owl#'}
                class_count = 0
                subclass_count = 0
                object_property_count = 0
                object_property_domain_count = 0
                annotation_count = 0
                subobject_property_count = 0
                annotation_assertion_count = 0
                object_min_cardinality_count = 0
                object_union_count = 0

                # Parse Classes
                for path in class_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for classes at path: {path}{Style.RESET_ALL}")
                    classes_found = root.findall(path, ns)
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Found {len(classes_found)} classes at {path}{Style.RESET_ALL}")
                        for cls in classes_found:
                            click.echo(f"{Fore.YELLOW}Class IRI: {cls.get('abbreviatedIRI')}{Style.RESET_ALL}")
                    for cls in classes_found:
                        iri = cls.get('abbreviatedIRI')
                        if iri:
                            class_count += 1
                            jsonld_graph["@graph"].append({
                                "@id": iri,
                                "@type": "Class"
                            })

                # Parse Object Properties
                for path in object_property_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for object properties at path: {path}{Style.RESET_ALL}")
                    for obj_prop in root.findall(path, ns):
                        iri = obj_prop.get('abbreviatedIRI')
                        if iri:
                            object_property_count += 1
                            jsonld_graph["@graph"].append({
                                "@id": iri,
                                "@type": "ObjectProperty"
                            })

                # Parse SubClassOf relationships
                for path in subclass_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for subclasses at path: {path}{Style.RESET_ALL}")
                    for subclass_of in root.findall(path, ns):
                        classes = subclass_of.findall('Class', ns)
                        if len(classes) == 2:
                            subclass_iri = classes[0].get('abbreviatedIRI')
                            superclass_iri = classes[1].get('abbreviatedIRI')
                            if subclass_iri and superclass_iri:
                                subclass_count += 1
                                subclass_entry = next((item for item in jsonld_graph["@graph"] if item["@id"] == subclass_iri), None)
                                if not subclass_entry:
                                    jsonld_graph["@graph"].append({
                                        "@id": subclass_iri,
                                        "@type": "Class",
                                        "rdfs:subClassOf": {"@id": superclass_iri}
                                    })
                                else:
                                    subclass_entry["rdfs:subClassOf"] = {"@id": superclass_iri}

                # Parse SubObject Properties
                for path in subobject_property_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for subobject properties at path: {path}{Style.RESET_ALL}")
                    for subobject_prop in root.findall(path, ns):
                        sub_props = subobject_prop.findall('ObjectProperty', ns)
                        if len(sub_props) == 2:
                            sub_iri = sub_props[0].get('abbreviatedIRI')
                            super_iri = sub_props[1].get('abbreviatedIRI')
                            if sub_iri and super_iri:
                                subobject_property_count += 1
                                sub_entry = next((item for item in jsonld_graph["@graph"] if item["@id"] == sub_iri and item["@type"] == "ObjectProperty"), None)
                                if not sub_entry:
                                    jsonld_graph["@graph"].append({
                                        "@id": sub_iri,
                                        "@type": "ObjectProperty",
                                        "rdfs:subPropertyOf": {"@id": super_iri}
                                    })
                                else:
                                    sub_entry["rdfs:subPropertyOf"] = {"@id": super_iri}

                # Parse Object Property Domains
                for path in object_property_domain_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for object property domains at path: {path}{Style.RESET_ALL}")
                    for obj_prop_domain in root.findall(path, ns):
                        obj_prop = obj_prop_domain.find('ObjectProperty', ns)
                        cls = obj_prop_domain.find('Class', ns)
                        if obj_prop is not None and cls is not None:
                            prop_iri = obj_prop.get('abbreviatedIRI')
                            class_iri = cls.get('abbreviatedIRI')
                            if prop_iri and class_iri:
                                object_property_domain_count += 1
                                prop_entry = next((item for item in jsonld_graph["@graph"] if item["@id"] == prop_iri and item["@type"] == "ObjectProperty"), None)
                                if not prop_entry:
                                    jsonld_graph["@graph"].append({
                                        "@id": prop_iri,
                                        "@type": "ObjectProperty",
                                        "rdfs:domain": {"@id": class_iri}
                                    })
                                else:
                                    prop_entry["rdfs:domain"] = {"@id": class_iri}

                # Parse Object Unions
                for path in object_property_domain_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for object unions within ObjectPropertyDomain at path: {path}{Style.RESET_ALL}")
                    for obj_prop_domain in root.findall(path, ns):
                        union = obj_prop_domain.find('ObjectUnionOf', ns)
                        if union is not None:
                            classes = union.findall('Class', ns)
                            if classes:
                                class_iris = [cls.get('abbreviatedIRI') for cls in classes if cls.get('abbreviatedIRI')]
                                obj_prop = obj_prop_domain.find('ObjectProperty', ns)
                                if obj_prop is not None and class_iris:
                                    prop_iri = obj_prop.get('abbreviatedIRI')
                                    if prop_iri:
                                        object_union_count += 1
                                        jsonld_graph["@graph"].append({
                                            "@type": "ObjectUnionOf",
                                            "property": {"@id": prop_iri},
                                            "classes": [{"@id": iri} for iri in class_iris]
                                        })

                # Parse Object Minimum Cardinalities
                for path in object_min_cardinality_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for object minimum cardinalities at path: {path}{Style.RESET_ALL}")
                    for subclass_of in root.findall(path, ns):
                        cls = subclass_of.find('Class', ns)
                        min_card = subclass_of.find('DataMinCardinality', ns)
                        if cls is not None and min_card is not None:
                            class_iri = cls.get('abbreviatedIRI')
                            prop = min_card.find('DataProperty', ns)
                            cardinality = min_card.get('cardinality')
                            if class_iri and prop is not None and cardinality:
                                prop_iri = prop.get('abbreviatedIRI')
                                if prop_iri:
                                    object_min_cardinality_count += 1
                                    jsonld_graph["@graph"].append({
                                        "@type": "DataMinCardinality",
                                        "class": {"@id": class_iri},
                                        "property": {"@id": prop_iri},
                                        "cardinality": cardinality
                                    })

                # Parse Annotations
                for path in annotation_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for annotations at path: {path}{Style.RESET_ALL}")
                    for annotation in root.findall(path, ns):
                        prop = annotation.find('AnnotationProperty', ns)
                        literal = annotation.find('Literal', ns)
                        if prop is not None and literal is not None:
                            prop_iri = prop.get('abbreviatedIRI')
                            literal_value = literal.text
                            if prop_iri and literal_value:
                                annotation_count += 1
                                jsonld_graph["@graph"].append({
                                    "@type": "Annotation",
                                    "property": {"@id": prop_iri},
                                    "value": literal_value
                                })

                # Parse Annotation Assertions
                for path in annotation_assertion_paths:
                    if verbose_mode >= 2:
                        click.echo(f"{Fore.YELLOW}Searching for annotation assertions at path: {path}{Style.RESET_ALL}")
                    for assertion in root.findall(path, ns):
                        prop = assertion.find('AnnotationProperty', ns)
                        iri_elem = assertion.find('abbreviatedIRI', ns)
                        literal = assertion.find('Literal', ns)
                        if prop is not None and iri_elem is not None and literal is not None:
                            prop_iri = prop.get('abbreviatedIRI')
                            target_iri = iri_elem.text
                            literal_value = literal.text
                            if prop_iri and target_iri and literal_value:
                                annotation_assertion_count += 1
                                jsonld_graph["@graph"].append({
                                    "@type": "AnnotationAssertion",
                                    "property": {"@id": prop_iri},
                                    "target": {"@id": target_iri},
                                    "value": literal_value
                                })

                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_count} standalone object properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subclass_count} subclasses to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subobject_property_count} subobject properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_domain_count} object property domains to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_union_count} object unions to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_min_cardinality_count} object minimum cardinalities to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {annotation_count} annotations to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {annotation_assertion_count} annotation assertions to JSON-LD{Style.RESET_ALL}")
                return jsonld_graph
            except ET.ParseError as e:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.RED}Failed to parse XML: {e}{Style.RESET_ALL}")
                return jsonld_graph
        elif kg_url.lower().endswith('.jsonld'):
            try:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Loaded Knowledge Graph as JSON-LD from {kg_url}{Style.RESET_ALL}")
                json_data = json.loads(kg_content)
                class_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'Class')
                subclass_count = sum(1 for item in json_data.get('@graph', []) if item.get('rdfs:subClassOf'))
                object_property_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'ObjectProperty' and 'rdfs:domain' not in item)
                object_property_domain_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'ObjectProperty' and 'rdfs:domain' in item)
                annotation_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'Annotation')
                subobject_property_count = sum(1 for item in json_data.get('@graph', []) if item.get('rdfs:subPropertyOf'))
                annotation_assertion_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'AnnotationAssertion')
                object_min_cardinality_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'DataMinCardinality')
                object_union_count = sum(1 for item in json_data.get('@graph', []) if item.get('@type') == 'ObjectUnionOf')
                if verbose_mode >= 1:
                    click.echo(f"{Fore.YELLOW}Converted {class_count} classes to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_count} standalone object properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subclass_count} subclasses to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {subobject_property_count} subobject properties to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_property_domain_count} object property domains to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_union_count} object unions to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {object_min_cardinality_count} object minimum cardinalities to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {annotation_count} annotations to JSON-LD{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Converted {annotation_assertion_count} annotation assertions to JSON-LD{Style.RESET_ALL}")
                return json_data
            except json.JSONDecodeError as e:
                if verbose_mode >= 1:
                    click.echo(f"{Fore.RED}Failed to parse JSON-LD: {e}{Style.RESET_ALL}")
                return jsonld_graph
        else:
            if verbose_mode >= 1:
                click.echo(f"{Fore.YELLOW}Unsupported file format for {kg_url}{Style.RESET_ALL}")
            return jsonld_graph

    except Exception as e:
        if verbose_mode >= 1:
            click.echo(f"{Fore.RED}Unexpected error: {str(e)}{Style.RESET_ALL}")
        return jsonld_graph
