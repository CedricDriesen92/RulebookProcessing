from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal, BNode
import uuid
import textwrap

# Namespaces
SH = Namespace("http://www.w3.org/ns/shacl#")
FBB = Namespace("https://ontology.firebim.be/ontology/fbo#")

def clean_string_for_mermaid(s):
    """Clean and escape a string for Mermaid"""
    # Replace newlines and multiple spaces
    s = ' '.join(s.split())
    # Escape special characters
    s = s.replace('"', '\\"')
    s = s.replace('{', '\\{')
    s = s.replace('}', '\\}')
    s = s.replace('\n', '\\ ')
    # Truncate if too long
    if len(s) > 50:
        s = s[:47] + "..."
    return s

def node_id_for_uri(uri):
    """Generate a mermaid-safe node id from a URI or literal"""
    # Mermaid requires alphanumeric and underscore for node IDs
    base_id = uri if isinstance(uri, str) else str(uri)
    base_id = base_id.replace("http://", "").replace("https://", "")
    base_id = base_id.replace("/", "_").replace("#", "_").replace(":", "_")
    # If too long, shorten
    if len(base_id) > 50:
        base_id = base_id[:50]
    # Ensure it starts with a letter for safety
    if not base_id[0].isalpha():
        base_id = "n_" + base_id
    return base_id

def ensure_node(uri, lines, label=None, node_map={}):
    """Ensure a node exists in the diagram and return its ID"""
    if uri not in node_map:
        nid = node_id_for_uri(uri) + "_" + str(uuid.uuid4())[:8]
        node_map[uri] = nid
        # Add node definition line with styling for logical operators
        node_label = label if label else uri
        node_label = clean_string_for_mermaid(str(node_label))
        if label and label.startswith('[') and label.endswith(']'):
            # Style for logical operators
            lines.append(f'{nid}["{node_label}"]:::logicalOperator')
        else:
            lines.append(f'{nid}["{node_label}"]')
    return node_map[uri]

def handle_logical_operator(g, shape_uri, operator_node, shape_id, lines, node_map):
    """Handle logical operators (sh:and, sh:or, sh:not, sh:xone)"""
    operator_type = None
    
    # Determine the operator type
    if (shape_uri, SH.or_, operator_node) in g:
        operator_type = "OR"
    elif (shape_uri, SH.and_, operator_node) in g:
        operator_type = "AND"
    elif (shape_uri, SH.not_, operator_node) in g:
        operator_type = "NOT"
    elif (shape_uri, SH.xone, operator_node) in g:
        operator_type = "XONE"
    
    if not operator_type:
        return

    # Create operator node
    operator_id = ensure_node(str(operator_node), lines, label=f"[{operator_type}]", node_map=node_map)
    lines.append(f"{shape_id} --> {operator_id}")

    # Process all triples where this operator is the subject
    for s, p, o in g:
        if s == operator_node:
            if isinstance(o, (URIRef, BNode)):
                # For objects that might be nodes themselves
                obj_id = ensure_node(str(o), lines, label=str(o).split('#')[-1], node_map=node_map)
                lines.append(f"{operator_id} --> {obj_id}")
                # Recursively process this node
                process_node(g, o, obj_id, lines, node_map)
            else:
                # For literal values
                value_id = ensure_node(f"{str(operator_node)}_{str(p)}_{str(o)}", lines, 
                                    label=f"{p.split('#')[-1]}={clean_string_for_mermaid(str(o))}", 
                                    node_map=node_map)
                lines.append(f"{operator_id} --> {value_id}")

def process_node(g, node, node_id, lines, node_map):
    """Process any node and its properties"""
    # Handle all triples where this node is the subject
    for s, p, o in g:
        if s == node:
            if p in [SH.and_, SH.or_, SH.not_, SH.xone]:
                # Special handling for logical operators
                handle_logical_operator(g, node, o, node_id, lines, node_map)
            else:
                # For all other predicates
                if isinstance(o, (URIRef, BNode)):
                    # For objects that might be nodes themselves
                    obj_id = ensure_node(str(o), lines, label=str(o).split('#')[-1], node_map=node_map)
                    # Add edge with label using proper Mermaid syntax
                    edge_label = clean_string_for_mermaid(str(p).split('#')[-1])
                    lines.append(f"{node_id} -- {edge_label} --> {obj_id}")
                    # Recursively process this node
                    process_node(g, o, obj_id, lines, node_map)
                else:
                    # For literal values
                    value_id = ensure_node(f"{str(node)}_{str(p)}_{str(o)}", lines, 
                                        label=f"{p.split('#')[-1]}={clean_string_for_mermaid(str(o))}", 
                                        node_map=node_map)
                    lines.append(f"{node_id} --> {value_id}")

def generate_mermaid_from_shacl(shapes_file, output_file="diagram.mmd"):
    g = Graph()
    g.parse(shapes_file, format="turtle")

    # Start a Mermaid diagram
    lines = [
        "graph TD",
        "classDef logicalOperator fill:#f9f,stroke:#333,stroke-width:2px;",
        "classDef constraint fill:#e1f5fe,stroke:#333,stroke-width:1px;",
        "classDef property fill:#f1f8e9,stroke:#333,stroke-width:1px;",
        "classDef shape fill:#fff3e0,stroke:#333,stroke-width:2px;"
    ]

    # Query all NodeShapes
    node_shapes = g.query("""
        SELECT ?shape
        WHERE {
            ?shape a sh:NodeShape .
        }
    """)

    # We'll keep track of assigned node ids to avoid duplicates
    node_map = {}

    for row in node_shapes:
        shape_uri = row[0]
        shape_id = ensure_node(str(shape_uri), lines, label=str(shape_uri.split('#')[-1]))
        
        # Process all properties of the shape
        process_node(g, shape_uri, shape_id, lines, node_map)

    # Write to output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Mermaid diagram generated: {output_file}")

if __name__ == "__main__":
    # Example usage:
    # Adjust 'shapes.ttl' to point to your SHACL file.
    #shapes_file = "casestudy_compartmentarea/shapes.ttl"
    #mermaid_file = "casestudy_compartmentarea/mermaid.txt"
    shapes_file = "shacl_shapes_mmd\BasisnormenLG_cropped.pdf\section_2_1_shapes.ttl"
    mermaid_file = "temp_mermaid.txt"
    generate_mermaid_from_shacl(shapes_file, mermaid_file)
