from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
import uuid
import textwrap

# Namespaces
SH = Namespace("http://www.w3.org/ns/shacl#")
FBB = Namespace("http://example.com/ontology/fbb#") # Example namespace used in previous code

def generate_mermaid_from_shacl(shapes_file, output_file="diagram.mmd"):
    g = Graph()
    g.parse(shapes_file, format="turtle")

    # Start a Mermaid diagram
    # Using a top-down (TD) layout for clarity
    lines = ["graph TD"]

    # Query all NodeShapes
    # A NodeShape is indicated by rdf:type sh:NodeShape
    node_shapes = g.query("""
        SELECT ?shape
        WHERE {
            ?shape a sh:NodeShape .
        }
    """)

    # We'll keep track of assigned node ids to avoid duplicates
    # key: uri (string), value: mermaid node id (string)
    node_map = {}

    def node_id_for_uri(uri):
        # Generate a mermaid-safe node id from a URI or literal
        # Mermaid requires alphanumeric and underscore for node IDs
        # We'll generate a short uuid if it's a blank node
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

    def ensure_node(uri, label=None):
        # Create a new node for uri if not exists
        if uri not in node_map:
            nid = node_id_for_uri(uri) + "_" + str(uuid.uuid4())[:8]
            node_map[uri] = nid
            # Add node definition line
            node_label = label if label else uri
            # Escape quotes
            node_label = node_label.replace('"', '\\"')
            lines.append(f'{nid}["{node_label}"]')
        return node_map[uri]

    # For each NodeShape, we find:
    # - Target class (sh:targetClass)
    # - Property shapes (sh:property)
    # - SPARQL constraints (sh:select, sh:ask within SHACL)
    for row in node_shapes:
        shape_uri = row[0]
        shape_id = ensure_node(str(shape_uri), label=str(shape_uri.split('#')[-1]))
        
        # Link to target classes
        for tclass in g.objects(shape_uri, SH.targetClass):
            tclass_id = ensure_node(str(tclass), label="Class: " + str(tclass.split('#')[-1]))
            lines.append(f"{shape_id} --> {tclass_id}")

        # Find SPARQL constraints: sh:rule, sh:constraint (SPARQL-based)
        for sparql_constraint in g.objects(shape_uri, SH.rule):
            select_query = g.value(sparql_constraint, SH.select)
            construct_query = g.value(sparql_constraint, SH.construct)
            query_text = select_query if select_query else construct_query
            if query_text:
                # Remove leading spaces
                query_text = textwrap.dedent(query_text)
                # Extract first comment (text after # and before newline)
                comment = query_text.split('\n')[1].strip()
                if comment.startswith('#'):
                    comment = comment[1:].strip()
                c_id = ensure_node(str(sparql_constraint), label="SPARQL: " + comment)
                lines.append(f"{shape_id} --> {c_id}")

        for sparql_constraint in g.objects(shape_uri, SH.constraint):
            select_query = g.value(sparql_constraint, SH.select)
            ask_query = g.value(sparql_constraint, SH.ask)
            query_text = select_query if select_query else ask_query
            if query_text:
                # Remove leading spaces
                query_text = textwrap.dedent(query_text)
                # Extract first comment (text after # and before newline)
                comment = query_text.split('\n')[1].strip()
                if comment.startswith('#'):
                    comment = comment[1:].strip()
                c_id = ensure_node(str(sparql_constraint), label="SPARQL: " + comment)
                lines.append(f"{shape_id} --> {c_id}")

        # Property shapes
        # Each property shape can define constraints like sh:datatype, sh:maxExclusive, etc.
        for pshape in g.objects(shape_uri, SH.property):
            pshape_id = ensure_node(str(pshape), label="Property Rule")
            lines.append(f"{shape_id} --> {pshape_id}")

            # Find the path (the property it constrains)
            path = g.value(pshape, SH.path)
            if path:
                path_id = ensure_node(str(path), label="Property: " + str(path).split('#')[-1])
                lines.append(f"{pshape_id} --> {path_id}")

            # Find constraints like sh:maxExclusive, sh:datatype, etc.
            # We'll just list them all
            for pred, obj in g.predicate_objects(pshape):
                if pred.startswith(SH) and pred not in [SH.path]:
                    # This is a SHACL constraint property
                    # We'll represent each constraint as a node or a note
                    constraint_id = ensure_node(str(pshape) + str(pred) + str(obj),
                                                label=str(pred.split('#')[-1]) + "=" + str(obj))
                    lines.append(f"{pshape_id} --> {constraint_id}")

    # Write to output file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Mermaid diagram generated: {output_file}")

if __name__ == "__main__":
    # Example usage:
    # Adjust 'shapes.ttl' to point to your SHACL file.
    generate_mermaid_from_shacl("casestudy_compartmentarea/shapes.ttl", "casestudy_compartmentarea/mermaid.txt")
