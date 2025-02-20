import os
from rdflib import Graph, RDF, Namespace, URIRef
from dotenv import load_dotenv

load_dotenv()

keyword_mapping = {
    '0': ['Low Building', 'General'],
    '1': ['Low Building'],
    '2': ['Low Building', 'Compartmentation'],
    '3': ['Low Building', 'Construction Elements'],
    '4': ['Low Building'],
    '5': ['Low Building'],
    '1_1': ['Firefighting'],
    '2_2': ['Evacuation', 'Exits', 'Complex'],
    '3_5_1_2': ['Complex'],
    '4_1': ['Compartmentation'],
    '4_2_2': ['Complex'],
}

FIREBIM = Namespace("http://example.com/firebim#")

input_file = os.getenv("INPUT_FILE")
document_name = f"documentgraphs/{input_file}"
def combine_ttl_files(document_name):
    input_folder = document_name
    combined_graph = Graph()
    combined_graph.bind('fbd', FIREBIM)

    for ttl_file in os.listdir(input_folder):
        if ttl_file.endswith('.ttl') and ttl_file != 'combined.ttl':
            file_path = os.path.join(input_folder, ttl_file)
            section_number = ttl_file.replace('.ttl', '').replace('section_', '') # Extract section number from filename
            section_graph = Graph() # Create a graph for each section
            section_graph.parse(file_path, format='turtle')

            # Apply keywords to the section graph
            if section_number in keyword_mapping:
                section_uri = None  # URI of the section, needs to be extracted from the graph
                for s, p, o in section_graph.triples((None, RDF.type, FIREBIM.Section)): # Assuming sections are of type firebim:Section
                    section_uri = s # Assuming there is only one section per file, or we take the first one

                if section_uri: # Only proceed if a section URI is found in the graph
                    for keyword_str in keyword_mapping[section_number]:
                        keyword_uri = URIRef(FIREBIM[keyword_str.replace(' ', '_')])
                        section_graph.add((keyword_uri, RDF.type, FIREBIM.Keyword))
                        section_graph.add((section_uri, FIREBIM.hasKeyword, keyword_uri))


            combined_graph += section_graph # Merge the section graph into the combined graph

    combined_file_path = os.path.join(input_folder, 'combined.ttl')
    combined_graph.serialize(destination=combined_file_path, format='turtle')
    print(f"Combined TTL file created at: {combined_file_path}")

def main():
    combine_ttl_files(document_name)

if __name__ == "__main__":
    main()

