import sys
from rdflib import Graph, Namespace, URIRef, RDFS
from rdflib.namespace import RDF

SH = Namespace("http://www.w3.org/ns/shacl#")
FIREBIM = Namespace("http://example.com/firebim#")
FBB = Namespace("http://example.com/firebimbuilding#")

# Templates for common constraints
CONSTRAINT_TEMPLATES = {
    str(SH.minInclusive): "The {property} must be at least {value}.",
    str(SH.maxInclusive): "The {property} must be at most {value}.",
    str(SH.minCount): "There must be at least {value} {property}(s).",
    str(SH.maxCount): "There must be at most {value} {property}(s).",
    #str(SH.datatype): "The {property} must be a {value} datatype.",
    str(SH.hasValue): "The {property} must be exactly {value}."
}

# Symbols for each indentation level
# Level 0: no symbol
# Level 1: '-'
# Level 2: '•'
# Level 3: '◆'
indentation_symbols = ["", "\t", "\t\t-", "\t\t\t•", "\t\t\t\t◆"]

def format_line(level: int, text: str) -> str:
    """
    Format a line with appropriate indentation and symbol based on level.
    Level 0: no symbol, no indent
    Level 1: '- ' prefix
    Level 2: '• ' prefix
    Level 3: '◆ ' prefix
    Additional indentation can be added if needed, but here we just use symbols.
    """
    if level < len(indentation_symbols):
        symbol = indentation_symbols[level]
    else:
        # If we exceed known levels, just reuse the last symbol
        symbol = indentation_symbols[-1]
    
    prefix = symbol + " " if symbol else ""
    return prefix + text

def get_label(graph, uri):
    """Get a human-friendly label for a URI from the ontology. Falls back to local name."""
    uri_ref = URIRef(uri)
    lbls = list(graph.objects(uri_ref, RDFS.label))
    if lbls:
        return str(lbls[0])
    # Fallback: extract local part
    if "#" in uri:
        return uri.split("#")[-1]
    return uri.rsplit("/", 1)[-1]

def describe_property_shape(shapes_graph, ontology_graph, prop_shape, indent=0):
    """
    Convert a property shape into human-readable sentences based on known constraints.
    """
    descriptions = []
    path = list(shapes_graph.objects(prop_shape, SH.path))
    if not path:
        return descriptions
    property_uri = path[0]
    property_label = get_label(ontology_graph, property_uri)

    # Handle known constraints
    for constraint_pred, template in CONSTRAINT_TEMPLATES.items():
        for constraint_val in shapes_graph.objects(prop_shape, URIRef(constraint_pred)):
            if constraint_pred == str(SH.datatype):
                val_label = get_label(ontology_graph, constraint_val)
            elif constraint_pred == str(SH.hasValue):
                val_str = str(constraint_val)
                if val_str.lower() in ['true', 'false']:
                    val_label = val_str.lower()
                else:
                    val_label = get_label(ontology_graph, constraint_val)
            else:
                val_label = str(constraint_val)
            desc = template.format(property=property_label, value=val_label)
            
            # Add severity if specified
            severity = list(shapes_graph.objects(prop_shape, SH.severity))
            if severity:
                severity_label = get_label(ontology_graph, severity[0])
                desc += f" (Severity: {severity_label})"
            
            descriptions.append(format_line(indent, desc))

    return descriptions

def describe_node_constraint(shapes_graph, ontology_graph, node_shape, indent=0):
    """
    Describe a node shape and its constraints.
    """
    descriptions = []

    # Add rule source if present
    rule_sources = list(shapes_graph.objects(node_shape, FIREBIM.rulesource))
    if rule_sources:
        source_label = get_label(ontology_graph, rule_sources[0])
        descriptions.append(format_line(indent, f"Rule source: {source_label}"))

    # Add flowchart node IDs if present
    flowchart_nodes = list(shapes_graph.objects(node_shape, FBB.flowchartNodeID))
    if flowchart_nodes:
        nodes_str = ", ".join([str(node) for node in flowchart_nodes])
        descriptions.append(format_line(indent, f"Flowchart nodes: {nodes_str}"))
        
    # Identify the target class
    target_classes = list(shapes_graph.objects(node_shape, SH.targetClass))
    if target_classes:
        class_label = get_label(ontology_graph, target_classes[0])
        descriptions.append(format_line(indent, f"For every {class_label}:"))

    # Handle SPARQL rules (simplistic)
    for rule in shapes_graph.objects(node_shape, SH.rule):
        if (rule, RDF.type, SH.SPARQLRule) in shapes_graph:
            construct_query = list(shapes_graph.objects(rule, SH.construct))
            if construct_query:
                descriptions.append(format_line(indent+1, "Has SPARQL validation rule:"))
                query_text = str(construct_query[0])
                message = None
                if "sh:resultMessage" in query_text:
                    parts = query_text.split('sh:resultMessage "')
                    if len(parts) > 1:
                        message_part = parts[1].split('"', 1)[0]
                        message = message_part
                if message:
                    descriptions.append(format_line(indent+2, f"Message: {message}"))
                # Conditions from WHERE clause (simplified)
                if "WHERE {" in query_text:
                    where_part = query_text.split('WHERE {')[1].split('}')[0]
                    descriptions.append(format_line(indent+2, "Conditions:"))
                    for line in where_part.strip().split('\n'):
                        line = line.strip()
                        if line and not line.startswith('FILTER'):
                            parts = line.split()
                            if len(parts) >= 3 and parts[1].startswith('fbb:'):
                                prop_label = get_label(ontology_graph, URIRef("http://example.com/firebimbuilding#" + parts[1][4:]))
                                descriptions.append(format_line(indent+3, f"{prop_label} must be {parts[2]}"))
                        elif line.startswith('FILTER'):
                            descriptions.append(format_line(indent+3, line))

            # Add severity if specified
            severity = list(shapes_graph.objects(rule, SH.severity))
            if severity:
                severity_label = get_label(ontology_graph, severity[0])
                descriptions.append(format_line(indent+2, f"(Severity: {severity_label})"))

    # Property shapes
    property_shapes = list(shapes_graph.objects(node_shape, SH.property))
    for pshape in property_shapes:
        prop_descs = describe_property_shape(shapes_graph, ontology_graph, pshape, indent+1)
        descriptions.extend(prop_descs)

    and_prop = SH["and"]
    or_prop = SH["or"]

    # Logical constraints: AND
    and_list = list(shapes_graph.objects(node_shape, and_prop))
    if and_list:
        descriptions.append(format_line(indent+1, "ALL of the following must be true:"))
        and_shapes = rdf_list_to_python_list(shapes_graph, and_list[0])
        for shape in and_shapes:
            sub_descs = describe_subshape(shapes_graph, ontology_graph, shape, indent+2)
            descriptions.extend(sub_descs)

    # Logical constraints: OR
    or_list = list(shapes_graph.objects(node_shape, or_prop))
    if or_list:
        descriptions.append(format_line(indent+1, "AT LEAST ONE of the following must be true:"))
        or_shapes = rdf_list_to_python_list(shapes_graph, or_list[0])
        for shape in or_shapes:
            sub_descs = describe_subshape(shapes_graph, ontology_graph, shape, indent+2)
            descriptions.extend(sub_descs)

    return descriptions

def describe_subshape(shapes_graph, ontology_graph, shape_uri, indent=0):
    """
    Describe a shape referenced in sh:and or sh:or.
    This might be a NodeShape or a PropertyShape or a blank node with constraints.
    """
    descriptions = []

    is_node_shape = (shape_uri, RDF.type, SH.NodeShape) in shapes_graph
    is_property_shape = (shape_uri, RDF.type, SH.PropertyShape) in shapes_graph

    and_prop = SH["and"]
    or_prop = SH["or"]

    # If it's a property shape, describe properties
    if is_property_shape:
        prop_descs = describe_property_shape(shapes_graph, ontology_graph, shape_uri, indent)
        descriptions.extend(prop_descs)

    # If it's a node shape, handle property shapes inside it and nested logic
    if is_node_shape:
        property_shapes = list(shapes_graph.objects(shape_uri, SH.property))
        for pshape in property_shapes:
            prop_descs = describe_property_shape(shapes_graph, ontology_graph, pshape, indent)
            descriptions.extend(prop_descs)

        and_list = list(shapes_graph.objects(shape_uri, and_prop))
        if and_list:
            descriptions.append(format_line(indent, "ALL of these must be true:"))
            and_shapes = rdf_list_to_python_list(shapes_graph, and_list[0])
            for s in and_shapes:
                sub_descs = describe_subshape(shapes_graph, ontology_graph, s, indent+1)
                descriptions.extend(sub_descs)

        or_list = list(shapes_graph.objects(shape_uri, or_prop))
        if or_list:
            descriptions.append(format_line(indent, "AT LEAST ONE of these must be true:"))
            or_shapes = rdf_list_to_python_list(shapes_graph, or_list[0])
            for s in or_shapes:
                descriptions.append(format_line(indent+1, "Option:"))
                sub_descs = describe_subshape(shapes_graph, ontology_graph, s, indent+2)
                descriptions.extend(sub_descs)

    # If it's neither explicitly a node nor property shape, it might be a blank node with constraints
    if not is_node_shape and not is_property_shape:
        property_shapes = list(shapes_graph.objects(shape_uri, SH.property))
        for pshape in property_shapes:
            prop_descs = describe_property_shape(shapes_graph, ontology_graph, pshape, indent)
            descriptions.extend(prop_descs)

        and_list = list(shapes_graph.objects(shape_uri, and_prop))
        if and_list:
            descriptions.append(format_line(indent, "ALL of these must be true:"))
            and_shapes = rdf_list_to_python_list(shapes_graph, and_list[0])
            for s in and_shapes:
                sub_descs = describe_subshape(shapes_graph, ontology_graph, s, indent+1)
                descriptions.extend(sub_descs)

        or_list = list(shapes_graph.objects(shape_uri, or_prop))
        if or_list:
            descriptions.append(format_line(indent, "AT LEAST ONE of these must be true:"))
            or_shapes = rdf_list_to_python_list(shapes_graph, or_list[0])
            for s in or_shapes:
                descriptions.append(format_line(indent+1, "Option:"))
                sub_descs = describe_subshape(shapes_graph, ontology_graph, s, indent+2)
                descriptions.extend(sub_descs)

    return descriptions

def rdf_list_to_python_list(graph, list_node):
    """
    Given an RDF list node, return a Python list of items.
    RDF lists are typically represented using rdf:first, rdf:rest.
    """
    items = []
    current = list_node
    while current and current != RDF.nil:
        first = list(graph.objects(current, RDF.first))
        if first:
            items.extend(first)
        rest = list(graph.objects(current, RDF.rest))
        current = rest[0] if rest else None
    return items

def process_shacl_files(shapes_file_path: str, ontology_file_path: str) -> list[str]:
    """
    Process SHACL shapes and ontology files and return a list of constraint descriptions.
    """
    ontology_graph = Graph()
    ontology_graph.parse(ontology_file_path, format="turtle")

    shapes_graph = Graph()
    shapes_graph.parse(shapes_file_path, format="turtle")

    # Find all NodeShapes
    node_shapes = list(shapes_graph.subjects(RDF.type, SH.NodeShape))
    
    all_descriptions = []
    for ns in node_shapes:
        desc = describe_node_constraint(shapes_graph, ontology_graph, ns, indent=0)
        all_descriptions.extend(desc)
        all_descriptions.append("")  # blank line between shapes
    
    return all_descriptions

if __name__ == "__main__":
    # Example usage with proper path formatting
    shapes_file = r"shacl_shapes_mmd/BasisnormenLG_cropped.pdf/section_2_1_shapes.ttl"
    ontology_file = r"casestudy_compartmentarea/fbb.ttl"
    output_file = r"temp_output_shacltotxt.txt"
    descriptions = process_shacl_files(shapes_file, ontology_file)
    with open(output_file, "w", encoding="utf-8") as f:
        for line in descriptions:
            f.write(line + "\n")
            print(line)
