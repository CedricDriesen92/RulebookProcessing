import os
import glob
import csv
from rdflib import Graph, Namespace
from anthropic import AnthropicVertex
import anthropic
import time
from dotenv import load_dotenv

load_dotenv()

anthropic_key = os.getenv("ANTHROPIC_API_KEY")

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")
SHACL = Namespace("http://www.w3.org/ns/shacl#")
SH = Namespace("http://www.w3.org/ns/shacl#")

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def load_csv(file_path):
    with open(file_path, 'r') as file:
        return list(csv.DictReader(file))

def process_mmd_to_shacl(mmd_content, ontology, base_name, objects_data, properties_data, text_content):
    prompt = f"""
You are an AI assistant specialized in converting FireBIM rules represented in Mermaid (.mmd) diagram format into SHACL shapes. Your task is to create SHACL shapes that can be used to validate building graphs following the FireBIM building ontology.

Here's the FireBIM building ontology for reference:

{ontology}

Given the following Mermaid diagram content representing FireBIM rules, as well as its source text file, create SHACL shapes that capture these rules. Include SPARQL or PythonIfcOpenShell code within the SHACL shapes where necessary to fully represent the rule's logic.

Mermaid diagram content:
{mmd_content}
The source text:
{text_content}

Please output only the SHACL shapes in Turtle format, without any explanations. Ensure that your output is valid Turtle syntax and uses the appropriate SHACL vocabulary.

Use the following prefixes:
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix fbb: <http://example.com/firebimbuilding#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

Remember to:
1. Make sure the shape(s) defined follow the Mermaid chart completely, making sure that it can be checked first try (this means no placeholder functions, everything should be explicit)
2. Use sh:property to define property constraints.
3. Use sh:sparql for complex rules that require SPARQL queries.
4. Use sh:pyFn for rules that require Python and IfcOpenShell logic (embedding Python code as a string).
5. Assign meaningful names to your shapes, preferably based on the section or article IDs from the original rules.
6. Add a link to the document ontology by using sh:yourshape firebim:rulesource (use this exact term: "firebim:rulesource", the yourshape should be replaced by the relevant name) firebim:yoursource (this should link to the section the rule is from originally, which is {base_name.capitalize()}).
7. Use the exact URIs provided in the Mermaid diagram for all relevant entities and properties.
8. Optimize the SHACL shapes for clarity, conciseness, and effectiveness in rule validation.

Start your output with the prefix declarations mentioned above, then provide the SHACL shapes.
"""
    prompt_verify = f"""
Your task is to check the given SHACL shapes and make sure they are a perfect recreation of their original text and mermaid (based on the text) diagram, but in SHACL+SPARQL+Python format. They are based on the FireBIM building ontology and should adhere to its or any inherited definitions.

Here's the FireBIM building ontology for reference:

{ontology}

Here is the source Mermaid diagram content representing FireBIM rules. Based on this, please correct the SHACL shapes so that they perfectly capture these rules. Include SPARQL or PythonIfcOpenShell code within the SHACL shapes where necessary to fully represent the rule's logic.

Mermaid diagram content:
{mmd_content}
The source text:
{text_content}

Please output only the SHACL shapes in Turtle format, without any explanations. Ensure that your output is valid Turtle syntax and uses the appropriate SHACL vocabulary.

Use the following prefixes:
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix fbb: <http://example.com/firebimbuilding#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

Remember to:
1. Make sure the shape(s) defined follow the Mermaid chart completely, making sure that it can be checked first try (this means no placeholder functions, everything should be explicit)
2. Use sh:property to define property constraints.
3. Use sh:sparql for complex rules that require SPARQL queries.
4. Use sh:pyFn for rules that require Python and IfcOpenShell logic (embedding Python code as a string).
5. Assign meaningful names to your shapes, preferably based on the section or article IDs from the original rules.
6. Add a link to the document ontology by using sh:yourshape firebim:rulesource (use this exact term: "firebim:rulesource", the yourshape should be replaced by the relevant name) firebim:yoursource (this should link to the section the rule is from originally, which is {base_name.capitalize()}).
7. Use the exact URIs provided in the Mermaid diagram for all relevant entities and properties.
8. Optimize the SHACL shapes for clarity, conciseness, and effectiveness in rule validation.

Start your output with the prefix declarations mentioned above, then provide the SHACL shapes. Nothing else.

Here is the draft of the SHACL file:
"""
    while True:
        try:
            response = client.messages.create(
                max_tokens=8000,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                model="claude-3-5-sonnet-v2@20241022"
            )
            final_response = client.messages.create(
                max_tokens=8000,
                messages=[
                    {"role": "user", "content": prompt_verify + "\n" + response.content[0].text.strip()},
                ],
                model="claude-3-5-sonnet-v2@20241022"
            )
            return final_response.content[0].text.strip()
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)

def main():
    ontology = load_ontology('buildingontologies/firebimSource.ttl')
    objects_data = load_csv('MatrixObjects.csv')
    properties_data = load_csv('MatrixProperties.csv')
    input_folder = 'mmddiagrams'
    output_folder = 'shacl_shapes_mmd'
    text_source_folder = 'trainingsamplesRuleToGraph'

    os.makedirs(output_folder, exist_ok=True)

    for mmd_file in glob.glob(os.path.join(input_folder, '*.mmd')):
        base_name = os.path.splitext(os.path.basename(mmd_file))[0]
        output_file = os.path.join(output_folder, f"{base_name}_shapes.ttl")
        text_file = os.path.join(text_source_folder, f"{base_name}.txt")
        if '2_1' in base_name:
            if os.path.exists(output_file):
                print(f"SHACL shapes for {base_name} already exist. Skipping.")
                continue

            with open(mmd_file, 'r', encoding='utf-8') as f:
                mmd_content = f.read()
                
            with open(text_file, 'r', encoding='utf-8') as f:
                text_content = f.read()

            shacl_shapes = process_mmd_to_shacl(mmd_content, ontology, base_name, objects_data, properties_data, text_content)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(shacl_shapes)

            print(f"Generated SHACL shapes for {base_name}")
        else:
            print(f"Skipping {base_name}")

    print("SHACL shape generation complete.")

if __name__ == "__main__":
    main()