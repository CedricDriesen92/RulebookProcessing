import os
from rdflib import Graph
from dotenv import load_dotenv

load_dotenv()

input_file = os.getenv("INPUT_FILE")
document_name = f"documentgraphs/{input_file}"
def combine_ttl_files(document_name):
    input_folder = document_name
    combined_graph = Graph()

    for ttl_file in os.listdir(input_folder):
        if ttl_file.endswith('.ttl') and ttl_file != 'combined.ttl':
            file_path = os.path.join(input_folder, ttl_file)
            combined_graph.parse(file_path, format='turtle')

    combined_file_path = os.path.join(input_folder, 'combined.ttl')
    combined_graph.serialize(destination=combined_file_path, format='turtle')
    print(f"Combined TTL file created at: {combined_file_path}")

def main():
    combine_ttl_files(document_name)

if __name__ == "__main__":
    main()

