import csv
import glob
import os
import json
import xml.etree.ElementTree as ET
from xmlrpc import client
from anthropic import Anthropic
from anthropic import AnthropicVertex
from lxml import etree
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
from pyshacl import validate
import time

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def load_csv(file_path):
    with open(file_path, 'r') as file:
        return list(csv.DictReader(file))

def process_shacl_to_ids(shacl_content, ontology, objects_data, properties_data, examples_str):
    prompt = f"""
You are an AI assistant specialized in converting SHACL shapes into BuildingSmart IDS (Information Delivery Specification) files. Your task is to transform the given SHACL shapes, based on the FireBIM building ontology, into equivalent IDS definitions that can validate building information models.

Given the following SHACL shape content:

{shacl_content}

Please generate a corresponding IDS definition in the appropriate format that approximates the SHACL checks as closely as possible. Ensure that:
1. All constraints defined in the SHACL shapes are accurately reflected in the IDS definitions.
2. The IDS definitions use appropriate schemas and follow best coding practices.
3. The code is clean, well-organized, and includes necessary comments for complex logic.
4. The IDS definitions can be executed without errors and effectively perform the intended validations.
If parts of the SHACL shapes are too complex, describe them in a single comment block at the end of the IDS definition, in the .

Please output ONLY the IDS definition without any explanations.
"""

    prompt_verify = f"""
Please review the IDS definition generated below and make any necessary corrections to ensure it fully and accurately implements the SHACL shapes provided. The IDS definition should strictly adhere to the rules defined in the SHACL shapes and utilize the FireBIM building ontology correctly.

Here is the SHACL shape content:

{shacl_content}

And here is the generated IDS definition:

# IDS Definition Start
{shacl_content}  # Replace this with the actual IDS definition generated in the previous step
# IDS Definition End

Please output ONLY the corrected IDS definition without any explanations.
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
            final_response = client.messages.create(
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt_verify + "\n" + response.content[0].text.strip()},
                ],
                model="claude-3-5-sonnet@20240620"
            )
            return final_response.content[0].text.strip()
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)

def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    objects_data = load_csv('MatrixObjects.csv')
    properties_data = load_csv('MatrixProperties.csv')
    with open('schema_ids.txt', 'r') as file:
        schema_ids = file.read()
    input_folder = 'shacl_shapes_mmd'
    output_folder = 'ids_output'

    os.makedirs(output_folder, exist_ok=True)

    for shacl_file in glob.glob(os.path.join(input_folder, '*.ttl')):
        base_name = os.path.splitext(os.path.basename(shacl_file))[0]
        output_file = os.path.join(output_folder, f"{base_name}_ids.ids")

        if os.path.exists(output_file):
            print(f"IDS for {base_name} already exists. Skipping.")
            continue

        with open(shacl_file, 'r', encoding='utf-8') as f:
            shacl_content = f.read()

        ids_definition = process_shacl_to_ids(shacl_content, ontology, objects_data, properties_data, schema_ids)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(ids_definition)

        print(f"Generated IDS file for {base_name}")

    print("IDS generation complete.")

if __name__ == "__main__":
    main()
