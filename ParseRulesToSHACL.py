import os
import tempfile
import rdflib
from rdflib import Graph
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

# Main execution
if __name__ == "__main__":
    # Path to local directory containing .txt ontology files
    local_path = "buildingontologies/"
    
    # Output path for the merged ontology
    output_path = "buildingontologies/result/merged_ontology.owl"
    
    # Load ontologies
    merged_ontology = load_ontologies(local_path)
    
    # Save merged ontology
    #if merged_ontology:
        #save_merged_ontology(merged_ontology, output_path)
    
    data_graph = rdflib.Graph().parse("buildinggraphs/Article2_1_1BE_Data.ttl", format="turtle")
    shapes_graph = rdflib.Graph().parse("shaclshapes/Article2_1_1BE_Shapes.ttl", format="turtle")
    #data_graph.print()
    #shapes_graph.print()
    #print(shapes_graph)
    r = validate(data_graph, shacl_graph=shapes_graph, debug=False, inference="none", advanced=True)
    conforms, results_graph, results_text = r
    print(conforms)
    results_graph.print()