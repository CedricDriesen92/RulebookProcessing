import os
import tempfile
import rdflib
from rdflib import Graph
import shutil

def convert_ttl_to_xml(input_path, filepath_short, output_format='xml'):
    g = rdflib.Graph()
    try:
        g.parse(input_path, format='turtle')
        # Create a temporary file
        with open(filepath_short + ".xml", mode='w') as temp_file:
            g.serialize(destination=temp_file.name, format=output_format)
            return temp_file.name
    except Exception as e:
        print(f"Error converting {input_path}: {str(e)}")
        return None

def load_ontologies(uris, local_path):
    ontologies = ["BOTen", "BPOen", "GEOsparqlen", "OPMen"]
    
    filename_source = "firebimSource.txt"
    if filename_source.endswith('.txt'):
        file_path = os.path.join(local_path, filename_source)
        file_path_short = file_path[:file_path.find(".")]
        try:
            if xml_path:
                main_onto = rdflib.Graph().parse(file_path, format="turtle")
                print(f"Loaded ontology from file: {filename_source}")
        except Exception as e:
            print(f"Error loading ontology from file {filename_source}: {str(e)}")
            print(f"Error loading ontology from URI {uri}: {str(e)}")
    
    # Convert and load ontologies from local text files
    for filename in ontologies:
        file_path = os.path.join(local_path, filename + ".txt")
        file_path_short = file_path[:file_path.rfind(".")]
        try:
            onto = get_ontology(f"file://{xml_path}").load()
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
    # List of URIs for ontologies
    uris = [
        "https://schemas.opengis.net/indoorgml/1.0/indoorgmlcore.xsd",
        "https://schemas.opengis.net/indoorgml/1.0/indoorgmlnavi.xsd"
    ]
    
    # Path to local directory containing .txt ontology files
    local_path = "buildingontologies/"
    
    # Output path for the merged ontology
    output_path = "buildingontologies/result/merged_ontology.owl"
    
    # Load ontologies
    merged_ontology = load_ontologies(uris, local_path)
    
    # Save merged ontology
    if merged_ontology:
        save_merged_ontology(merged_ontology, output_path)