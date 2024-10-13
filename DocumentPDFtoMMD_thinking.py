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
        reader = csv.reader(file)
        next(reader)  # Skip header row
        return [row[0] for row in reader]

def process_ttl_to_mmd(ttl_content, ontology, objects_data, properties_data, examples_str):
    prompt = f"""
Your task is to think about how to generate complete Mermaid flowcharts for automated compliance checking.

Given the following text files representing part of a rule document, try to think about how you would create a Mermaid diagram that shows detailed algorithms to solve the rules described. This will serve as input for a later LLM that will generate the actual diagram.

Important guidelines:
1. Only use objects and properties from the provided tables!! If, for some reason, a new object or property needs to be defined first think if it can be replaced by one from the tables, and if not mark it in red for a new object and purple for a new property!
2. Use markdown to color all object names pink and all property names blue in the Mermaid diagram. Also create an URL following the examples given later in the prompt.
3. Provide the full, complete pseudocode for each rule.
4. Ensure the Mermaid syntax is correct and can be directly used in a .mmd file.
5. Provide clear pass/fail results wherever possible, otherwise make everything as clear as possible as to what should happen.
6. Try to make the flowchart really pseudocode-like, close to the way a real code file (in Python, or SHACL, or C) would do these checks.
7. Follow the style guidelines given in the examples very closely. Be aware that the objects and properties in the examples might NOT be the same as the ones given to you, ALWAYS use the ones from the tables given later in the prompt.
8. Make sure that the flowchart is complete, and that it EXACTLY follows the rule as presented in the text. EVERY decision and every action has to be included, and every possible path has to be shown.
9. For actions that are vague in the text, use subcharts to make a proposal for how this should be checked. Again, see the examples and how they handle this.
10. For clarity format everything using rectangles (using [] like in the examples), except for the starting point and pass/fail points, references, notes...
11. To reiterate, there should not be any uncertainty to the meaning of the words in the diagram, every construction or fire related words needs to come from the tables and always has to be referenced correctly as specified earlier. EVERY SINGLE NODE that's NOT the start or end node needs AT LEAST ONE URI!!! As an example, instead of "is a duplex" you can use the property "IsDuplex", this says the same but in a referenced way so the work can always be checked easily and is not open for interpretation.

Objects table:
{objects_data}

Properties table:
{properties_data}

Training examples, follow these examples closely. Note that these examples might be incomplete and lack object/property matching:
{examples_str}

Begin by enclosing all thoughts within <thinking> tags, exploring multiple angles and approaches.
Break down the solution into clear steps within <step> tags. Use <count> tags after each step to show the step you are on.
Continuously adjust your reasoning based on intermediate results and reflections, adapting your strategy as you progress.
Regularly evaluate progress using <reflection> tags. Be critical and honest about your reasoning process.
Assign a quality score between 0.0 and 1.0 using <reward> tags after each reflection. Use this to guide your approach:

0.8+: Continue current approach
0.5-0.7: Consider minor adjustments
Below 0.5: Seriously consider backtracking and trying a different approach


If unsure or if reward score is low, backtrack and try a different approach, explaining your decision within <thinking> tags.
For mathematical problems, show all work explicitly using LaTeX for formal notation and provide detailed proofs.
Explore multiple solutions individually if possible, comparing approaches in reflections.
Use thoughts as a scratchpad, writing out all calculations and reasoning explicitly.
Synthesize the final answer within <answer> tags, providing a clear, concise summary.
Conclude with a final reflection on the overall solution, discussing effectiveness, challenges, and solutions. Assign a final reward score.That concludes the prompt. Now, for the actual content to be transformed:

{ttl_content}
"""
    prompt_verify = f"""
You are specialized in converting rulebook sections represented in text format into Mermaid diagrams. Your task is to create complete Mermaid flowcharts for automated compliance checking.

Given the following text files representing part of a rule document, as well as an in-depth thought process on how to best approach this, create an EXPLICIT mermaid diagram that shows detailed algorithms to solve the rules described. Make sure nothing in this diagram is vague, it has to contain all the info in the text pertaining to rules and rule checking, and that everything that could be objects or properties mentioned are from the tables you will receive and have the correct URI attached.

Important guidelines:
1. Only use objects and properties from the provided tables!! If, for some reason, a new object or property needs to be defined first think if it can be replaced by one from the tables, and if not mark it in red for a new object and purple for a new property!
2. Use markdown to color all object names pink and all property names blue in the Mermaid diagram. Also create an URL following the examples given later in the prompt.
3. Provide the full, complete pseudocode for each rule.
4. Ensure the Mermaid syntax is correct and can be directly used in a .mmd file.
5. Provide clear pass/fail results wherever possible, otherwise make everything as clear as possible as to what should happen.
6. Try to make the flowchart really pseudocode-like, close to the way a real code file (in Python, or SHACL, or C) would do these checks.
7. Follow the style guidelines given in the examples very closely. Be aware that the objects and properties in the examples might NOT be the same as the ones given to you, ALWAYS use the ones from the tables given later in the prompt.
8. Make sure that the flowchart is complete, and that it EXACTLY follows the rule as presented in the text. EVERY decision and every action has to be included, and every possible path has to be shown.
9. For actions that are vague in the text, use subcharts to make a proposal for how this should be checked. Again, see the examples and how they handle this.
10. For clarity format everything using rectangles (using [] like in the examples), except for the starting point and pass/fail points, references, notes...
11. To reiterate, there should not be any uncertainty to the meaning of the words in the diagram, every construction or fire related words needs to come from the tables and always has to be referenced correctly as specified earlier. EVERY SINGLE NODE that's NOT the start or end node needs AT LEAST ONE URI!!! As an example, instead of "is a duplex" you can use the property "IsDuplex", this says the same but in a referenced way so the work can always be checked easily and is not open for interpretation.

Objects table:
{objects_data}

Properties table:
{properties_data}

Training examples, follow these examples closely. Note that these examples might be incomplete and lack object/property matching:
{examples_str}

Please output ONLY the Mermaid diagram, without any explanations, as pure text (not in a code block). Ensure that your output is valid in syntax, and that it contains the appropriate naming conventions and color specifications. Your output will be put directly into a .mmd file, it will not be processed further.

This is the original text:

{ttl_content}

Now, here is the mmd to be checked, again ONLY output the revised mmd file, not in code blocks:
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
            first_answer = response.content[0].text.strip()
            first_answer = first_answer.replace("{", "[").replace("}", "]")
            print(f"First answer: {first_answer}")
            final_response = client.messages.create(
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt_verify + "\n\n" + first_answer},
                ],
                model="claude-3-5-sonnet@20240620"
            )
            second_answer = final_response.content[0].text.strip()
            print(f"Final answer: {second_answer}")
            return second_answer
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)

def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    objects_data = load_csv('MatrixObjects_auto.csv')
    properties_data = load_csv('MatrixProperties_auto.csv')
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

        if os.path.exists(output_file) or "n_3_5" not in base_name:
            print(f"Skipping {base_name}.")
            continue
        
        with open(txt_file, 'r', encoding='utf-8') as f:
            txt_content = f.read()

        mmd_diagram = process_ttl_to_mmd(txt_content, ontology, objects_data, properties_data, examples_str)

        with open(output_file, 'w', encoding='utf-8') as f:
            #f.write("---\ntitle: " + base_name + "\n---\n")
            f.write(mmd_diagram)

        print(f"Generated Mermaid diagram for {base_name}")

    print("Mermaid generation complete.")

if __name__ == "__main__":
    main()