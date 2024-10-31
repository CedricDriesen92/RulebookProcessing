import os
import rdflib
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from pyshacl import validate



def load_ontologies(local_path):
    """
    Loads and merges multiple ontology files into a single graph.
    First loads the main source file (firebimSource.ttl) then adds other ontologies to it.
    """
    ontologies = ["BOTen", "BPOen", "GEOsparqlen", "OPMen"]
    
    filename_source = "firebimSource.ttl"
    file_path = os.path.join(local_path, filename_source)
    try:
        main_onto = rdflib.Graph().parse(file_path, format="turtle")
        print(f"Loaded ontology from file: {filename_source}")
    except Exception as e:
        print(f"Error loading ontology from file {filename_source}: {str(e)}")
    
    # Convert and load ontologies from local text files
    for filename in ontologies:
        file_path = os.path.join(local_path, filename + ".ttl")
        try:         
            onto = rdflib.Graph().parse(file_path, format="turtle")
            main_onto = main_onto + onto
        except Exception as e:
            print(f"Error loading ontology from file {filename}: {str(e)}")
    
    return main_onto

def load_document_data(file_path):
    return rdflib.Graph().parse(file_path, format="turtle")

def get_member_text(document_graph, member_id):
    firebim = Namespace("http://example.com/firebim#")
    member_uri = URIRef(f"http://example.com/firebim#Member_{member_id.replace('.', '_')}")
    original_text = document_graph.value(subject=member_uri, predicate=firebim.hasOriginalText)
    return str(original_text) if original_text else "Original text not found"

def parse_member_references(shapes_graph):
    """
    Extracts relationships between SHACL shapes and their corresponding member IDs.
    Maps both node shapes and their property shapes to member IDs for traceability.
    
    Returns: Dictionary mapping shape URIs to their member IDs
    """
    firebim = Namespace("http://example.com/firebim#")
    ex = Namespace("http://example.org/")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    member_refs = {}
    
    for shape, p, o in shapes_graph.triples((None, RDF.type, sh.NodeShape)):
        member_id = shapes_graph.value(subject=shape, predicate=firebim.rulesource)
        if member_id and 'Member' in member_id:
            member_refs[str(shape)] = str(member_id)
            # Also map property shapes to the same member ID
            for prop_shape in shapes_graph.objects(shape, sh.property):
                member_refs[str(prop_shape)] = str(member_id)
    print(member_refs)
    return member_refs

def get_section_text(document_graph, section_id):
    firebim = Namespace("http://example.com/firebim#")
    section_uri = URIRef(f"http://example.com/firebim#Section_{section_id.replace('.', '_')}")
    original_text = document_graph.value(subject=section_uri, predicate=firebim.hasOriginalText)
    return str(original_text) if original_text else "Original text not found"

def parse_section_references(shapes_graph):
    firebim = Namespace("http://example.com/firebim#")
    ex = Namespace("http://example.org/")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    section_refs = {}
    
    for shape, p, o in shapes_graph.triples((None, RDF.type, sh.NodeShape)):
        section_id = shapes_graph.value(subject=shape, predicate=firebim.rulesource)
        if section_id and 'Section' in section_id:
            section_refs[str(shape)] = str(section_id)
            # Also map property shapes to the same section ID
            for prop_shape in shapes_graph.objects(shape, sh.property):
                section_refs[str(prop_shape)] = str(section_id)
    print(section_refs)
    return section_refs

def find_parent_shape(results_graph, shape):
    sh = Namespace("http://www.w3.org/ns/shacl#")
    for parent in results_graph.subjects(sh.property, shape):
        if (parent, RDF.type, sh.NodeShape) in results_graph:
            return parent
    return None

def process_validation_results(results_graph, member_refs, section_refs, document_graph, html_file_name, shapes_graph):
    """
    Processes SHACL validation results and creates detailed violation reports.
    Links violations back to their source rules and original text.
    
    Returns: 
    - processed_results: List of dictionaries containing violation details
    - failed_nodes: Set of nodes that failed validation (for diagram highlighting)
    """
    sh = Namespace("http://www.w3.org/ns/shacl#")
    processed_results = []
    failed_nodes = set()
    
    for result, p, o in results_graph.triples((None, RDF.type, sh.ValidationResult)):
        source_shape = results_graph.value(subject=result, predicate=sh.sourceShape)
        severity = results_graph.value(subject=result, predicate=sh.resultSeverity)

        member_id = member_refs.get(str(source_shape), None)
        section_id = section_refs.get(str(source_shape), None)
        
        if member_id:
            original_text = get_member_text(document_graph, member_id)
            html_link = f"{html_file_name}#member-{member_id.replace('.', '-')}"
        elif section_id:
            original_text = get_section_text(document_graph, section_id)
            html_link = f"{html_file_name}#section-{section_id.replace('.', '-')}"
        else:
            original_text = "Text not found"
            html_link = ""

        processed_results.append({
            "severity": severity,
            "member_id": member_id if member_id else "Unknown",
            "section_id": section_id if section_id else "Unknown",
            "focus_node": str(results_graph.value(subject=result, predicate=sh.focusNode)),
            "message": str(results_graph.value(subject=result, predicate=sh.resultMessage)),
            "original_text": original_text,
            "source_shape": str(source_shape),
            "html_link": html_link
        })
    
    # Now, collect failed_nodes using the refined parse_flowchart_nodes
    failed_nodes = parse_flowchart_nodes(results_graph, shapes_graph)
    
    return processed_results, failed_nodes

def parse_flowchart_nodes(results_graph, shapes_graph):
    fbb = Namespace("http://example.com/firebimbuilding#")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    # Track nodes with their highest severity
    failed_nodes = {}  # Changed from set to dict to store severity

    try:
        for result in results_graph.subjects(RDF.type, sh.ValidationResult):
            try:
                source_shape = results_graph.value(subject=result, predicate=sh.sourceShape)
                severity = str(results_graph.value(subject=result, predicate=sh.resultSeverity))
                
                # Convert severity URI to simple string
                severity_level = severity.split('#')[-1].lower()
                
                def update_node_severity(node_id):
                    current_severity = failed_nodes.get(str(node_id), "info")
                    # Higher severity overwrites lower severity
                    if (severity_level == "violation" or 
                        (severity_level == "warning" and current_severity == "info") or
                        (severity_level == "info" and current_severity != "warning" and current_severity != "violation")):
                        failed_nodes[str(node_id)] = severity_level

                # Rest of the existing node collection logic, but using update_node_severity
                if isinstance(source_shape, rdflib.BNode):
                    parent_shapes = list(shapes_graph.subjects(sh.property, source_shape))
                    for parent_shape in parent_shapes:
                        node_ids = list(shapes_graph.objects(subject=parent_shape, predicate=fbb.flowchartNodeID))
                        for node_id in node_ids:
                            update_node_severity(node_id)
                    
                    prop_node_ids = list(shapes_graph.objects(subject=source_shape, predicate=fbb.flowchartNodeID))
                    for node_id in prop_node_ids:
                        update_node_severity(node_id)
                else:
                    node_ids = list(shapes_graph.objects(subject=source_shape, predicate=fbb.flowchartNodeID))
                    for node_id in node_ids:
                        update_node_severity(node_id)

            except Exception as e:
                print(f"Error processing validation result: {e}")
                continue

    except Exception as e:
        print(f"Error parsing validation results: {e}")
        return {}

    print(f"\nFailed Nodes with Severities: {failed_nodes}")
    return failed_nodes

def highlight_mermaid_diagram(mmd_content, failed_nodes):
    """
    Updates a Mermaid diagram to highlight nodes that failed validation.
    
    Args:
    - mmd_content: Original Mermaid diagram content
    - failed_nodes: Dictionary of node IDs and their violation severity
    
    Returns: Modified Mermaid diagram content with highlighted nodes
    """
    modified_lines = []
    
    # First pass: Remove any existing class definitions from nodes
    for line in mmd_content.split('\n'):
        skip_line = False
        for node in failed_nodes:
            if (line.strip() == f'{node}:::startClass' or 
                line.strip() == f'{node}:::passClass' or 
                line.strip() == f'{node}:::failClass' or 
                line.strip() == f'{node}:::info' or 
                line.strip() == f'{node}:::warning' or 
                line.strip() == f'{node}:::violation'):
                skip_line = True
                break
            if line.strip().startswith(f'{node}[') or line.strip().startswith(f'{node}('):
                line = line.split(':::')[0]
        
        if not skip_line:
            modified_lines.append(line)
    
    # Second pass: Add new severity-based classes
    final_lines = []
    class_definitions_added = False
    
    # Define visual styles for different severity levels
    for line in modified_lines:
        if line.strip().startswith('classDef') and not class_definitions_added:
            final_lines.append(line)
            # Add class definitions for different severity levels
            final_lines.append('classDef info fill:#ffff00,stroke:#333,stroke-width:2px')      # Yellow for info
            final_lines.append('classDef warning fill:#ffa500,stroke:#333,stroke-width:2px')   # Orange for warnings
            final_lines.append('classDef violation fill:#ff0000,stroke:#333,stroke-width:2px') # Red for violations
            class_definitions_added = True
        else:
            modified_line = line
            for node, severity in failed_nodes.items():
                if line.strip().startswith(f'{node}[') or line.strip().startswith(f'{node}('):
                    modified_line = line.rstrip() + f':::{severity}'
                    break
            final_lines.append(modified_line)
    
    # Add class definitions if not added before
    if not class_definitions_added:
        final_lines.append('classDef info fill:#ffff00,stroke:#333,stroke-width:2px')
        final_lines.append('classDef warning fill:#ffa500,stroke:#333,stroke-width:2px')
        final_lines.append('classDef violation fill:#ff0000,stroke:#333,stroke-width:2px')
    
    # Add class assignments for failed nodes at the end
    for node, severity in failed_nodes.items():
        final_lines.append(f'{node}:::{severity}')
    
    return '\n'.join(final_lines)

def load_shapes_graph(file_path):
    """Load SHACL shapes with robust error handling."""
    shapes_graph = rdflib.Graph()
    try:
        # Try different parsers in order of likelihood
        for parser in ["turtle", "nt", "n3", "xml"]:
            try:
                print(f"Attempting to parse shapes with {parser} parser...")
                shapes_graph.parse(file_path, format=parser)
                print(f"Successfully parsed shapes with {parser} parser")
                return shapes_graph
            except Exception as e:
                print(f"Failed to parse with {parser}: {str(e)}")
                continue
        
        # If all parsers fail, try reading the file manually and parse its contents
        print("Attempting manual file read...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            shapes_graph.parse(data=content, format="turtle")
            print("Successfully parsed shapes from file contents")
            return shapes_graph
            
    except Exception as e:
        print(f"Error loading shapes graph: {str(e)}")
        raise

# Main execution
if __name__ == "__main__":
    """
    Main execution flow:
    1. Load and merge ontologies
    2. Load data graph (the instance data to validate)
    3. Load SHACL shapes (validation rules)
    4. Load document graph (original text references)
    5. Run SHACL validation
    6. Process results and generate reports
    7. Create highlighted Mermaid diagrams for visualization
    8. Generate HTML report
    """
    # Path to local directory containing .txt ontology files
    local_path = "buildingontologies/"
    
    # Output path for the merged ontology
    output_path = "buildingontologies/result/merged_ontology.owl"
    
    # Load ontologies
    merged_ontology = load_ontologies(local_path)
    
    data_graph = rdflib.Graph().parse("buildinggraphs/section_2_1BE_Data.ttl", format="turtle")
    try:
        shapes_graph = load_shapes_graph("shacl_shapes_mmd/section_2_1_shapes.ttl")
    except Exception as e:
        print(f"Fatal error loading shapes: {str(e)}")
        exit(1)
    document_graph = load_document_data(r"documentgraphs/BasisnormenLG_cropped.pdf/combined_document_data_graph.ttl")

    member_refs = parse_member_references(shapes_graph)
    section_refs = parse_section_references(shapes_graph)
    
    r = validate(data_graph, shacl_graph=shapes_graph, debug=False, inference="none", advanced=True)
    conforms, results_graph, results_text = r
    results_graph.serialize(destination="results_graph.ttl", format="turtle")
    
    print(f"Validation {'passed' if conforms else 'failed'}")
    
    html_file_name = "BasisnormenLG_cropped.html"
    
    processed_results, failed_nodes = [], set()
    
    if not conforms:
        processed_results, failed_nodes = process_validation_results(
            results_graph, 
            member_refs, 
            section_refs, 
            document_graph, 
            html_file_name,
            shapes_graph
        )
        
        for result in processed_results:
            if result['member_id'] != "Unknown":
                print(f"Member {result['member_id']} validation failed:")
            elif result['section_id'] != "Unknown":
                print(f"Section {result['section_id']} validation failed:")
            else:
                print("Unknown element validation failed:")
            print(f"  Severity: {result['severity']}")
            print(f"  Focus Node: {result['focus_node']}")
            print(f"  Original Text: {result['original_text']}")
            if result['html_link']:
                print(f"  HTML Link: {result['html_link']}")
            print()

        # Highlight Mermaid Diagram
        if failed_nodes:
            shapes_file = "shacl_shapes_mmd/section_2_1_shapes.ttl"  # Your current shapes file
            mmd_file = shapes_file.replace('shacl_shapes_mmd/', 'mmddiagrams/').replace('_shapes.ttl', '.mmd')
            
            if os.path.exists(mmd_file):
                with open(mmd_file, 'r', encoding='utf-8') as f:
                    mmd_content = f.read()
                
                highlighted_content = highlight_mermaid_diagram(mmd_content, failed_nodes)
                
                highlighted_file = mmd_file.replace('.mmd', '_highlighted.mmd')
                with open(highlighted_file, 'w', encoding='utf-8') as f:
                    f.write(highlighted_content)
                print(f"Created highlighted diagram: {highlighted_file}")
    
    # Generate HTML report as per existing logic
    with open("validation_report.html", "w", encoding="utf-8") as f:
        f.write("<html><body>")
        f.write("<h1>Validation Report</h1>")
        for result in processed_results:
            if "info" in result['severity'].lower():
                violation_color = "green"
            elif "warning" in result['severity'].lower():
                violation_color = "orange"
            elif "violation" in result['severity'].lower():
                violation_color = "red"
            else:
                violation_color = "black"  # Default color
            
            f.write(f"<h2 style='color:{violation_color}';>Severity: {result['severity'].split('#')[-1]}</h2>")
            f.write(f"<p>Focus Node: {result['focus_node'].split('/')[-1]}</p>")
            if result['html_link']:
                f.write(f"<a href='{result['html_link']}'>Rule origin</a>")
            if result['member_id'] != "Unknown":
                f.write(f"<p>Member {result['member_id']}</p>")
            elif result['section_id'] != "Unknown":
                f.write(f"<p>Section {result['section_id']}</p>")
            f.write(f"<p>Original Text: {result['original_text']}</p>")
            f.write("<hr>")
        f.write("</body></html>")