import os
import tempfile
import rdflib
from rdflib import Graph, Namespace
from rdflib import URIRef
from rdflib.namespace import RDF
import shutil
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

def save_merged_ontology(merged_onto, output_path):
    try:
        merged_onto.save(file=output_path, format="rdfxml")
        print(f"Merged ontology saved to: {output_path}")
    except Exception as e:
        print(f"Error saving merged ontology: {str(e)}")



def parse_member_references(shapes_graph):
    ex = Namespace("http://example.org/")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    member_refs = {}
    for shape, p, o in shapes_graph.triples((None, RDF.type, sh.NodeShape)):
        member_id = shapes_graph.value(subject=shape, predicate=ex.validatesMember)
        if member_id:
            member_refs[str(shape)] = str(member_id)
    print("Member refs: ")
    print(member_refs)
    return member_refs

def process_validation_results(results_graph, member_refs):
    sh = Namespace("http://www.w3.org/ns/shacl#")
    processed_results = []
    for result, p, o in results_graph.triples((None, RDF.type, sh.ValidationResult)):
        source_shape = results_graph.value(subject=result, predicate=sh.sourceShape)
        print(str(source_shape))
        member_id = member_refs.get(str(source_shape), "Unknown")
        focus_node = results_graph.value(subject=result, predicate=sh.focusNode)
        result_message = results_graph.value(subject=result, predicate=sh.resultMessage)
        processed_results.append({
            "member_id": member_id,
            "source_shape": source_shape,
            "focus_node": str(focus_node),
            "message": str(result_message)
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
    
    data_graph = rdflib.Graph().parse("buildinggraphs/Article2_1_1BE_Data.ttl", format="turtle")
    shapes_graph = rdflib.Graph().parse("shaclshapes/Article2_1_1BE_Shapes.ttl", format="turtle")

    member_refs = parse_member_references(shapes_graph)
    
    r = validate(data_graph, shacl_graph=shapes_graph, debug=False, inference="none", advanced=True)
    conforms, results_graph, results_text = r
    results_graph.print()
    
    print(f"Validation {'passed' if conforms else 'failed'}")
    
    if not conforms:
        processed_results = process_validation_results(results_graph, member_refs)
        for result in processed_results:
            print(f"Member {result['member_id']} validation failed:")
            print(f"  Source Shape: {result['source_shape']}")
            print(f"  Focus Node: {result['focus_node']}")
            print(f"  Message: {result['message']}")
            print()