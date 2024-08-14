import os
import glob
from rdflib import Graph, Namespace
from anthropic import AnthropicVertex
import time

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")
SHACL = Namespace("http://www.w3.org/ns/shacl#")
SH = Namespace("http://www.w3.org/ns/shacl#")

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="spatial-conduit-420822")

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def process_ttl_to_shacl(ttl_content, ontology):
    prompt = f"""
You are an AI assistant specialized in converting FireBIM rules represented in Turtle (.ttl) format into SHACL shapes. Your task is to create SHACL shapes that can be used to validate building graphs following the FireBIM building ontology.

Here's the FireBIM building ontology for reference:

{ontology}

Given the following Turtle content representing FireBIM rules, create SHACL shapes that capture these rules. Include SPARQL or PythonIfcOpenShell code within the SHACL shapes where necessary to fully represent the rule's logic.

Turtle content:
{ttl_content}

Please output only the SHACL shapes in Turtle format, without any explanations. Ensure that your output is valid Turtle syntax and uses the appropriate SHACL vocabulary.

Use the following prefixes:
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix firebim: <http://example.com/firebim#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

Remember to:
1. Create a shape for each relevant class or property in the FireBIM ontology.
2. Use sh:property to define property constraints.
3. Use sh:sparql for complex rules that require SPARQL queries.
4. Use sh:pyFn for rules that require Python and IfcOpenShell logic (embedding Python code as a string).
5. Assign meaningful names to your shapes, preferably based on the section or article IDs from the original rules.
6. Add a link to the document ontology by using sh:yourshape firebim:rulesource (use this exact term: "firebim: rulesource", the yourshape and yoursource should be replaced by the relevant names) firebim:yoursource (this should link to the article the rule is from originally).

Start your output with the prefix declarations mentioned above, then provide the SHACL shapes.
"""
    while True:
        try:
            response = client.messages.create(
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                model="claude-3-5-sonnet@20240620"
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)

def main():
    ontology = load_ontology('firebimSource.ttl')
    input_folder = 'sections'
    output_folder = 'shacl_shapes'

    os.makedirs(output_folder, exist_ok=True)

    for ttl_file in glob.glob(os.path.join(input_folder, '*.ttl')):
        base_name = os.path.splitext(os.path.basename(ttl_file))[0]
        output_file = os.path.join(output_folder, f"{base_name}_shapes.ttl")

        if os.path.exists(output_file):
            print(f"SHACL shapes for {base_name} already exist. Skipping.")
            continue

        with open(ttl_file, 'r', encoding='utf-8') as f:
            ttl_content = f.read()

        shacl_shapes = process_ttl_to_shacl(ttl_content, ontology)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(shacl_shapes)

        print(f"Generated SHACL shapes for {base_name}")

    print("SHACL shape generation complete.")

if __name__ == "__main__":
    main()