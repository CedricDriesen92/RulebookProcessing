import os
import glob
import csv
from rdflib import Graph, Namespace
from anthropic import AnthropicVertex
import anthropic
import time
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

anthropic_key = os.getenv("ANTHROPIC_API_KEY")
google_key = os.getenv("GEMINI_API_KEY")
input_file = os.getenv("INPUT_FILE")
model_provider = os.getenv("MODEL_PROVIDER", "anthropic")

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")
SHACL = Namespace("http://www.w3.org/ns/shacl#")
SH = Namespace("http://www.w3.org/ns/shacl#")

# Initialize clients conditionally
if model_provider == "gemini":
    genai.configure(api_key=google_key)
    gemini_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 65536,
        "response_mime_type": "text/plain",
    }
else:
    client = anthropic.Anthropic(api_key=anthropic_key)

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def load_csv(file_path):
    with open(file_path, 'r') as file:
        return list(csv.DictReader(file))

def process_mmd_to_shacl(mmd_content, ontology, base_name, objects_data, properties_data, text_content):
    # Enhanced Gemini prompt
    gemini_prompt = f"""
You are an expert SHACL engineer converting FireBIM rules from Mermaid diagrams to SHACL. Follow these steps:

1. Analyze the Mermaid diagram structure and node relationships
2. Cross-reference with source text for exact requirements
3. Map Mermaid elements to ontology classes/properties:
   {ontology}
4. Implement these validation strategies:
   - Class inheritance checks using sh:class
   - Property value ranges with sh:datatype
   - SPARQL for cross-property validation
   - Python functions for geometric checks
5. Ensure these quality controls:
   - Every shape has fbb:flowchartNodeID
   - All SHACL properties use full URIs
   - SPARQL queries use BIND for variables
   - Python code is properly escaped
   - No markdown in output
   - ALL prefixes are included and defined as for example: @prefix sh: <http://www.w3.org/ns/shacl#> .

Input Structure:
=== Mermaid Diagram === (flowchart logic)
{mmd_content}

=== Source Text === (regulatory requirements)
{text_content}

=== Ontology Reference ===
{ontology}

Output Requirements:
1. Start with prefix declarations
2. Group related shapes using sh:and/sh:or
3. Use sh:severity sh:Violation
4. Include sh:message with rule numbers
5. Validate in this order: Class > Properties > Relationships > Custom Rules

Example Structure:
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix fbb: <http://example.com/firebimbuilding#> .

fbb:FireDoorShape
    a sh:NodeShape ;
    sh:targetClass fbb:FireDoor ;
    sh:property [
        sh:path fbb:fireRating ;
        sh:datatype xsd:integer ;
        sh:minInclusive 60 ;
    ] ;
    fbb:flowchartNodeID "B2" ;
    sh:rulesource fbb:{base_name.capitalize()} .

Output ONLY the final SHACL Turtle with no additional text.
"""

    prompt = f"""
You are an AI assistant specialized in converting FireBIM rules represented in Mermaid (.mmd) diagram format into SHACL shapes. Your task is to reflect on the optimal way to create such SHACL shapes that can be used to validate building graphs following the FireBIM building ontology, after which your reflection is sent to a second LLM to create the actual SHACL shapes.

Here's the FireBIM building ontology for reference:

{ontology}

Given the following Mermaid diagram content representing FireBIM rules, as well as its source text file, do the reflection on how to best create SHACL shapes that capture these rules. This can also include SPARQL or PythonIfcOpenShell code within the SHACL shapes where necessary to fully represent the rule's logic.

Remember to think about the following:
1. Make sure the shape(s) defined follow the Mermaid chart completely, making sure that it can be checked first try (this means no placeholder functions, everything should be explicit)
2. Use sh:property to define property constraints.
3. Use sh:sparql for complex rules that require SPARQL queries.
4. Use sh:pyFn for rules that require Python and IfcOpenShell logic (embedding Python code as a string).
5. Assign meaningful names to your shapes, preferably based on the section or article IDs from the original rules.
6. Add a link to the document ontology by using sh:yourshape fro:rulesource (use this exact term: "fro:rulesource", the yourshape should be replaced by the relevant name) fro:yoursource (this should link to the section the rule is from originally, which is {base_name.capitalize()}).
7. Use the exact URIs provided in the Mermaid diagram for all relevant entities and properties.
8. Optimize the SHACL shapes for clarity, conciseness, and effectiveness in rule validation.
9. Very important: give every shape a reference using fbb:flowchartNodeID (this should be the same as the node ID in the Mermaid diagram) to allow for easy mapping back to the original rule.

DO NOT WASTE IMPORTANT TOKENS ON OUTPUTTING THE SHACL ITSELF, that is reserved for the next LLM and everything that came before is to understand the task. Only output what comes next:
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
Conclude with a final reflection on the overall solution, discussing effectiveness, challenges, and solutions. Assign a final reward score.That concludes the prompt. 
"""
    prompt2 = f"""Mermaid diagram content:
{mmd_content}
The source text:
{text_content}
"""
    prompt_verify = f"""
Your task is to check the given SHACL shapes and make sure they are a perfect recreation of their original text and mermaid (based on the text) diagram, but in SHACL+SPARQL+Python format. They are based on the FireBIM building ontology and should adhere to its or any inherited definitions.

Here's the FireBIM building ontology for reference:

{ontology}

Here is the source Mermaid diagram content representing FireBIM rules. Based on this, please correct the SHACL shapes so that they perfectly capture these rules. Include SPARQL or PythonIfcOpenShell code within the SHACL shapes where necessary to fully represent the rule's logic.

Please output only the SHACL shapes in Turtle format, without any explanations. Ensure that your output is valid Turtle syntax and uses the appropriate SHACL vocabulary.

Use the following prefixes:
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix fbb: <http://example.com/firebimbuilding#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

Remember to:
1. Make sure the shape(s) defined follow the Mermaid chart completely, making sure that it can be checked first try (this means no placeholder functions, everything should be explicit)
2. Use sh:property to define property constraints.
3. Use sh:sparql for complex rules that require SPARQL queries.
4. Use sh:pyFn for rules that require Python and IfcOpenShell logic (embedding Python code as a string).
5. Assign meaningful names to your shapes, preferably based on the section or article IDs from the original rules.
6. Add a link to the document ontology by using sh:yourshape fro:rulesource (use this exact term: "fro:rulesource", the yourshape should be replaced by the relevant name) fro:yoursource (this should link to the section the rule is from originally, which is {base_name.capitalize()}).
7. Use the exact URIs provided in the Mermaid diagram for all relevant entities and properties.
8. Optimize the SHACL shapes for clarity, conciseness, and effectiveness in rule validation.
9. Very important: give every shape a reference using fbb:flowchartNodeID (this should be the same as the node ID in the Mermaid diagram) to allow for easy mapping back to the original rule. Example of formatting: C["Check Parking rules (see 5.2)"] should be translated to fbb:flowchartNodeID "C".

Start your output with the prefix declarations mentioned above, then provide the SHACL shapes. Nothing else.
"""
    prompt_verify2 = f"""Mermaid diagram content:
{mmd_content}
The source text:
{text_content}
"""
    while True:
        try:
            if model_provider == "anthropic":
                response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=8192,
                    temperature=0,
                    system=prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt2
                                }
                            ]
                        }
                    ]
                )
                
                final_response = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=8192,
                    temperature=0,
                    system=prompt_verify,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Here is the reflection: " + response.content[0].text.strip() + "\nAnd here the other info: " + prompt_verify2
                                }
                            ]
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix fbb: <http://example.com/firebimbuilding#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> ."""
                                }
                            ]
                        }
                    ]
                )
                shacl_output = final_response.content[0].text.strip()
                return f"""@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix fbb: <http://example.com/firebimbuilding#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n{shacl_output.strip()}"""
        
            elif model_provider == "gemini":
                model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash-thinking-exp-01-21",
                    generation_config={**gemini_config, "temperature": 0},
                    system_instruction=gemini_prompt
                )
                response = model.generate_content(
                    f"Mermaid Diagram:\n{mmd_content}\n\n"
                    f"Source Text:\n{text_content}\n\n"
                )
                shacl_output = response.text
                
            return shacl_output.strip()
        
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)

def load_articles_from_graph(graph_path):
    g = Graph()
    g.parse(graph_path, format="turtle")
    
    FIREBIM = Namespace("http://example.com/firebim#")
    articles = []
    
    query = """
    SELECT DISTINCT ?article ?articleText ?member ?memberText
    WHERE {
        ?article a fro:Article .
        OPTIONAL { ?article fro:hasOriginalText ?articleText }
        OPTIONAL {
            ?article fro:hasMember+ ?member .
            ?member fro:hasOriginalText ?memberText
        }
    }
    ORDER BY ?article ?member
    """
    
    results = g.query(query, initNs={'firebim': FIREBIM})
    
    current_article = None
    current_text = []
    
    for row in results:
        article_uri = str(row.article)
        if current_article != article_uri:
            if current_article is not None:
                articles.append({
                    'uri': current_article,
                    'text': '\n'.join(current_text)
                })
            current_article = article_uri
            current_text = []
            if row.articleText:
                current_text.append(str(row.articleText))
        if row.memberText:
            current_text.append(str(row.memberText))
    
    # Add the last article
    if current_article is not None:
        articles.append({
            'uri': current_article,
            'text': '\n'.join(current_text)
        })
    
    return articles

def main():
    ontology = load_ontology('buildingontologies/firebimSource.ttl')
    objects_data = load_csv('MatrixObjects.csv')
    properties_data = load_csv('MatrixProperties.csv')
    document_name = 'BasisnormenLG_cropped.pdf'
    document_base_name = os.path.splitext(document_name)[0]
    
    # Add rulebookprocessing to all paths
    base_path = 'RulebookProcessing'
    input_folder = f'mmddiagrams/{document_name}'
    output_folder = f'shacl_shapes_mmd/{document_name}'
    input_graph = f'documentgraphs/{document_name}/combined.ttl'
    
    # Load articles from TTL graph
    articles = load_articles_from_graph(input_graph)
    
    # Create article lookup dictionary
    article_lookup = {article['uri'].split('#')[-1]: article['text'] for article in articles}

    os.makedirs(output_folder, exist_ok=True)

    print(os.path.join(input_folder, '*.mmd'))

    for mmd_file in glob.glob(os.path.join(input_folder, '*.mmd')):
        base_name = os.path.splitext(os.path.basename(mmd_file))[0]
        output_file = os.path.join(output_folder, f"{base_name}_shapes.ttl")

        if '_' in base_name:
            if os.path.exists(output_file):
                print(f"SHACL shapes for {base_name} already exist. Skipping.")
                continue

            with open(mmd_file, 'r', encoding='utf-8') as f:
                mmd_content = f.read()

            # Get article text from lookup instead of file
            article_id = base_name.replace('Article_', '')
            text_content = article_lookup.get(f'Article_{article_id}', '')
            
            if not text_content:
                print(f"Warning: No text content found for {base_name}")
                continue

            shacl_shapes = process_mmd_to_shacl(mmd_content, ontology, base_name, objects_data, properties_data, text_content)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(shacl_shapes)

            print(f"Generated SHACL shapes for {base_name}")
        else:
            print(f"Skipping {base_name}")

    print("SHACL shape generation complete.")

if __name__ == "__main__":
    main()