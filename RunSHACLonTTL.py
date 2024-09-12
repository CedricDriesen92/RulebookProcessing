import os
import rdflib
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF
from pyshacl import validate

def load_ontologies(local_path):
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
    ex = Namespace("http://example.org/")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    member_refs = {}
    
    for shape, p, o in shapes_graph.triples((None, RDF.type, sh.NodeShape)):
        member_id = shapes_graph.value(subject=shape, predicate=ex.validatesMember)
        if member_id:
            member_refs[str(shape)] = str(member_id)
            # Also map property shapes to the same member ID
            for prop_shape in shapes_graph.objects(shape, sh.property):
                member_refs[str(prop_shape)] = str(member_id)
    
    return member_refs

def find_parent_shape(results_graph, shape):
    sh = Namespace("http://www.w3.org/ns/shacl#")
    for parent in results_graph.subjects(sh.property, shape):
        if (parent, RDF.type, sh.NodeShape) in results_graph:
            return parent
    return None

def process_validation_results(results_graph, member_refs, document_graph, html_file_name):
    sh = Namespace("http://www.w3.org/ns/shacl#")
    processed_results = []
    
    for result, p, o in results_graph.triples((None, RDF.type, sh.ValidationResult)):
        source_shape = results_graph.value(subject=result, predicate=sh.sourceShape)
        severity = results_graph.value(subject=result, predicate=sh.resultSeverity)
        source_shape_str = str(source_shape)
        
        # Try to find the member ID directly
        member_id = member_refs.get(source_shape_str, None)
        
        # If not found, try to find the parent shape
        if member_id is None:
            parent_shape = find_parent_shape(results_graph, source_shape)
            if parent_shape:
                member_id = member_refs.get(str(parent_shape), "Unknown")
            else:
                member_id = "Unknown"
        
        focus_node = results_graph.value(subject=result, predicate=sh.focusNode)
        result_message = results_graph.value(subject=result, predicate=sh.resultMessage)
        original_text = get_member_text(document_graph, member_id) if member_id != "Unknown" else "Text not found"
        
        # Create HTML link
        html_link = f"{html_file_name}#member-{member_id.replace('.', '-')}" if member_id != "Unknown" else ""
        
        processed_results.append({
            "severity": severity,
            "member_id": member_id,
            "focus_node": str(focus_node),
            "message": str(result_message),
            "original_text": original_text,
            "source_shape": source_shape_str,
            "html_link": html_link
        })
    
    return processed_results


# Main execution
if __name__ == "__main__":
    # Path to local directory containing .txt ontology files
    local_path = "buildingontologies/"
    
    # Output path for the merged ontology
    output_path = "buildingontologies/result/merged_ontology.owl"
    
    # Load ontologies
    merged_ontology = load_ontologies(local_path)
    
    data_graph = rdflib.Graph().parse("buildinggraphs/section_2_1BE_Data.ttl", format="turtle")
    shapes_graph = rdflib.Graph().parse("shacl_shapes_mmd/section_2_1_shapes.ttl", format="turtle")
    document_graph = load_document_data("combined_document_data_graph.ttl")

    member_refs = parse_member_references(shapes_graph)
    
    r = validate(data_graph, shacl_graph=shapes_graph, debug=False, inference="none", advanced=True)
    conforms, results_graph, results_text = r
    
    print(f"Validation {'passed' if conforms else 'failed'}")
    
    html_file_name = "fire_safety_regulations.html"
    
    if not conforms:
        processed_results = process_validation_results(results_graph, member_refs, document_graph, html_file_name)
        for result in processed_results:
            print(f"Member {result['member_id']} validation failed:")
            print(f"  Severity: {result['severity']}")
            print(f"  Focus Node: {result['focus_node']}")
    #        print(f"  Message: {result['message']}")
            print(f"  Original Text: {result['original_text']}")
    #        print(f"  Source Shape: {result['source_shape']}")
            if result['html_link']:
                print(f"  HTML Link: {result['html_link']}")
            print()

    # Generate a simple HTML report with clickable links
    with open("validation_report.html", "w", encoding="utf-8") as f:
        f.write("<html><body>")
        f.write("<h1>Validation Report</h1>")
        for result in processed_results:
            if "info" in result['severity'].lower():
                violation_color = "green"
            if "warning" in result['severity'].lower():
                violation_color = "orange"
            if "violation" in result['severity'].lower():
                violation_color = "red"
            f.write(f"<h2 style='color:{violation_color}';>Severity: {result['severity'].split('#')[-1]}</h2>")
            f.write(f"<p>Focus Node: {result['focus_node'].split('/')[-1]}</p>")
            if result['html_link']:
                f.write(f"<p>Member {result['member_id']}</p>")
                f.write(f"<p>Original Text: {result['original_text']}</p>")
                f.write(f"<p><a href='{result['html_link']}' target='_blank'>View in Document</a></p>")
            else:
                f.write(f"<p>Message: {result['message']}</p>")
            f.write("<hr>")
        f.write("</body></html>")