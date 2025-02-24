import os
import re
from rdflib import Graph, RDF, Namespace, URIRef, Literal
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
            section_graph = Graph()
            section_graph.parse(file_path, format='turtle')

            # Process all entities that might have text content
            for s, p, o in section_graph.triples((None, FIREBIM.hasOriginalText, None)):
                text = str(o)
                # Find all href links in the text using regex
                href_pattern = r'href="http://example\.com/firebimbuilding#([^"]*)"'
                matches = re.findall(href_pattern, text)
                
                # Add keywords for each match
                for keyword in matches:
                    keyword_uri = URIRef(FIREBIM[keyword])
                    section_graph.add((keyword_uri, RDF.type, FIREBIM.Keyword))
                    section_graph.add((s, FIREBIM.hasKeyword, keyword_uri))
                    #print(f"Added keyword {keyword} to {s}")

            combined_graph += section_graph # Merge the section graph into the combined graph

    # Serialize the combined graph
    combined_file_path = os.path.join(input_folder, 'combined.ttl')
    combined_graph.serialize(destination=combined_file_path, format='turtle')
    print(f"Combined TTL file created at: {combined_file_path}")

def main():
    combine_ttl_files(document_name)

if __name__ == "__main__":
    main()

