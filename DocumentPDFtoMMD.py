import os
import glob
import csv
from rdflib import Graph, Namespace
from anthropic import AnthropicVertex
import time

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")
SHACL = Namespace("http://www.w3.org/ns/shacl#")
SH = Namespace("http://www.w3.org/ns/shacl#")

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def load_training_examples(txt_path, training_path):
    examples = []
    for mmd_file in glob.glob(os.path.join(training_path, '*.mmd')):
        base_name = os.path.splitext(os.path.basename(mmd_file))[0]
        txt_file = os.path.join(txt_path, f"{base_name}.txt")
        
        if os.path.exists(txt_file):
            with open(txt_file, 'r', encoding='utf-8') as txt, open(mmd_file, 'r', encoding='utf-8') as mmd:
                examples.append({
                    "input": txt.read().strip(),
                    "output": mmd.read().strip()
                })
    
    return examples

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def load_csv(file_path):
    with open(file_path, 'r') as file:
        return list(csv.DictReader(file))

def process_ttl_to_mmd(ttl_content, ontology, objects_data, properties_data, examples_str):
    prompt = f"""
You are an AI assistant specialized in converting rulebook sections represented in text format into Mermaid diagrams. Your task is to create complete Mermaid flowcharts for every object and parameter involved, showing the complete flow an application should follow to check the rule.

Given the following text files representing part of a rule document, create an EXPLICIT mermaid diagram that shows detailed algorithms to solve the rules described. Make sure nothing in this diagram is vague, it has to contain all the info in the text pertaining to rules and rule checking.

Important guidelines:
1. Only use objects and properties from the provided tables.
2. Use markdown to color all object names pink and all property names blue in the Mermaid diagram. Also create an URL following the examples given later in the prompt.
3. Provide the full, complete pseudocode for each rule.
4. Ensure the Mermaid syntax is correct and can be directly used in a .mmd file.
5. Provide clear pass/fail results wherever possible, otherwise make everything as clear as possible as to what should happen.
6. Try to make the flowchart really pseudocode-like, close to the way a real codefile (in Python, or SHACL, or C) would do these checks.
7. Follow the style guidelines given in the examples very closely.
8. Make sure that the flowchart is complete, and that it EXACTLY follows the rule as presented in the text. EVERY decision and every action has to be included, and every possible path has to be shown.

Objects table:
{objects_data}

Properties table:
{properties_data}

Training examples, follow these examples closely:
{examples_str}

Please output ONLY the Mermaid diagram, without any explanations, as pure text (not in a code block). Ensure that your output is valid in syntax, and that it contains the appropriate naming conventions and color specifications. Your output will be put directly into a .mmd file, it will not be processed further.

That concludes the prompt. Now, for the actual content to be transformed:

{ttl_content}
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
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    objects_data = load_csv('MatrixObjects.csv')
    properties_data = load_csv('MatrixProperties.csv')
    input_folder = 'trainingsamplesRuleToGraph'
    training_folder = 'trainingsamplesRuleToMMD'
    output_folder = 'mmddiagrams'

    os.makedirs(output_folder, exist_ok=True)
    training_examples = load_training_examples(input_folder, training_folder)
    examples_str = "\n\n".join([f"Input:\n{ex['input']}\n\nExpected output:\n{str(ex['output'])}\n" for ex in training_examples])
    with open("current_training_total_mmd.txt", "w", encoding="utf-8") as f:
        f.write(examples_str)

    for txt_file in glob.glob(os.path.join(input_folder, '*.txt')):
        base_name = os.path.splitext(os.path.basename(txt_file))[0]
        output_file = os.path.join(output_folder, f"{base_name}.mmd")

        if os.path.exists(output_file) or "2_1" not in base_name:
            print(f"MMD for {base_name} already exists. Skipping.")
            continue
        
        with open(txt_file, 'r', encoding='utf-8') as f:
            txt_content = f.read()

        mmd_diagram = process_ttl_to_mmd(txt_content, ontology, objects_data, properties_data, examples_str)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(mmd_diagram)

        print(f"Generated Mermaid diagram for {base_name}")

    print("Mermaid generation complete.")

if __name__ == "__main__":
    main()