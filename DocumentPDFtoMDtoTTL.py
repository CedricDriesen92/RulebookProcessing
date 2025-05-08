import pypdf
import pymupdf
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
import rdflib
import json
from anthropic import AnthropicVertex
import anthropic
from typing import List, Dict
import re
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD, OWL
import os
import glob
import time
from llama_parse import LlamaParse
from sympy import true
from dotenv import load_dotenv
import os
import google.generativeai as genai
import pandas as pd
import datetime

load_dotenv()

# Define the current version
current_version = "0.1"
now = datetime.datetime.now().isoformat()

google_key = os.getenv("GEMINI_API_KEY")
input_file = os.getenv("INPUT_FILE")
model_provider = os.getenv("MODEL_PROVIDER", "anthropic")

if model_provider == "gemini":
    genai.configure(api_key=google_key)

    # Create the model
    genai.configure(api_key=google_key)
    gemini_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 65536,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
    model_name="gemini-2.5-pro-preview-03-25",
    generation_config=gemini_config,
    )

llamaparse_key = os.getenv("LLAMAPARSE_API_KEY")
if model_provider == "anthropic":
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=anthropic_key)

def load_ontology(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def load_training_examples(folder_path):
    examples = []
    for ttl_file in glob.glob(os.path.join(folder_path, '*.ttl')):
        base_name = os.path.splitext(os.path.basename(ttl_file))[0]
        txt_file = os.path.join(folder_path, f"{base_name}.txt")
        
        if os.path.exists(txt_file):
            with open(txt_file, 'r', encoding='utf-8') as txt, open(ttl_file, 'r', encoding='utf-8') as ttl:
                examples.append({
                    "input": txt.read().strip(),
                    "output": ttl.read().strip()
                })
    
    return examples

def extract_text_from_pdf(pdf_path: str) -> str:
    text = ""
    #with open(pdf_path, 'rb') as file:
        #reader = pypdf.PdfReader(file)
        
        #for page in reader.pages:
        #    text += page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) + "\n"
    text = LlamaParse(api_key=llamaparse_key, result_type="markdown", skip_diagonal_text=True, show_progress=True, parsing_instruction="Extract the text from the document in Markdown format, make sure all titles for sections/subsections/subsubsections keep their numbering").load_data(pdf_path)
    # Write the output of LlamaParse to a Markdown file
    output_filename = f"{pdf_path}.md"
    with open(output_filename, 'w', encoding='utf-8') as md_file:
        md_file.write(text[0].text)
    print(f"Markdown content written to: {output_filename}")
    return text[0].text

def split_into_sections(text):
    # Split the text into sections based on markdown headers
    sections = re.split(r'\n(?=# \d)', text)
    
    final_sections = []
    for section in sections:
        # Extract section number and title
        match = re.match(r'# (\d+(?:\.\d+)*)\s*(.*?)(?:\n|$)', section, re.DOTALL)
        if match:
            section_number = match.group(1)
            section_title = match.group(2).strip()
            section_content = section[match.end():].strip()
            
            final_sections.append((section_number, section_title, section_content))
            print(f"Matched section: {section_number} - {section_title[:30]}...")
        else:
            print("Unmatched content:", section[:50] + "...")
    
    print("Number of sections found:", len(final_sections))
    return final_sections

def create_empty_section_ttl(section_number):
    ttl_content = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix fro: <https://ontology.firebim.be/ontology/fro#> .
@base <https://ontology.firebim.be/ontology/fro#> .

fro:Section_{section_number.replace('.', '_')} a fro:Section ;
    fro:hasID "{section_number}" .
"""
    return ttl_content

FRO = Namespace("https://ontology.firebim.be/ontology/fro#")
XML = Namespace("http://www.w3.org/XML/1998/namespace")


def create_initial_graph():
    g = Graph()
    g.bind("fro", FRO)
    
    document = URIRef(FRO.RoyalDecree)
    authority = URIRef(FRO.Belgian_Government)
    
    g.add((document, RDF.type, FRO.Document))
    g.add((document, FRO.hasID, Literal("RoyalDecree1994")))
    g.add((document, FRO.issued, Literal("1994-07-07", datatype=XSD.date)))
    
    g.add((authority, RDF.type, FRO.Authority))
    g.add((authority, FRO.hasDocument, document))
    
    return g

def process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph):
    # Base ontology prompt
    prompt = f"""
You are tasked with converting building code rulebook sections into Turtle (.ttl) format following the FireBIM Document Ontology. Here's the complete ontology for your reference:

{ontology}

Here is some more info on the firebim ontology and how you should use it:

The firebim regulation ontology maps one-to-one to parts of the AEC3PO ontology, however, it is more lightweight, following best practices from the W3C Linked Building Data Community Group. It consists of three main classes, the fro:Authority (which represents the legal body that publishes and maintains the regulatory document), the fro:DocumentSubdivision (which represents documents or parts of documents), and the fro:Reference (which represents references to other representations of the regulation, or similar regulations). The fro:DocumentSubdivision class has a subclass tree that defines a document, a section, an article, and a member. The latter typically holds the one or multiple bodies of text that an article exists of. We introduce multiple types of sections, such as chapters, subchapters, paragraphs, appendices, tables, and figures.
The created data graph should be modeled as a tree structure with multiple members per article and multiple articles per paragraph. Members can contain submembers, or they can have references to other members, using the fro:hasBackwardReference and fro:hasForwardReference object properties. This enables members to refer to other members if they for example contain constraints for the other member, as could be seen in Figure 2. This first part of the FireBIM ontology stack does not semantically enrich the regulation or the building itself; the regulatory member text is simply added to the graph as a literal.

Not every section needs to have their own sections/articles/members, if the section text is empty no articles are needed...
In your .ttl, if your section is not a base numbered section (i.e. 0, 1, 2...) make a hasSection from the parent section to this section. Adding all originaltext, in order, from all DocumentSubdivisions should recreate the rules part of the document. For the section itself don't include the full originaltext, only the titles. Make everything that includes a subdivision of the title (e.g. 4.3.1.2 if you are doing section 4.3.1) its own section with as originaltext the title attached to the number, with the following text split up in articles, split up in members. NEVER repeat text, it should ALWAYS be used only once, ALL originaltext will be added automatically so any doubles ruin the format.
The subsection parsing goes until level 3 (e.g. 1.3.2), so if you are dealing with section 1.3 do not try to define section 1.3.2, it only complicates things later on.
Do not include prefix declarations or @base. Start directly with the triples for this section. Ensure the output is valid Turtle syntax that can be parsed when added to an existing graph.
Depending on the language of the source text, make sure to add language tags where necessary. Do not translate the original text in any way, keep the source perfectly accurate.
If a figure or table is implied in the text, make sure to declare it and add the required relations/properties. Even if you can't see it, it's still there.
Make sure every article consists of AT LEAST 1 member, these are the rule building blocks. However, not every higher-level document subdivision necessarily needs an article, since articles are about rules and checks and requirements. Also, members can have their own members. Articles and members don't necessarily need to have an originaltext, otherwise a text is provided with the members further dividing the requirements.
For text spanning multiple lines make sure to use triple quotes, as single codes will be invalid there. Also avoid using Paragraph, instead use Section.
Format text to be logical, don't change the content but fix any obvious formatting errors.
Output only the Turtle (.ttl) content, no explanations. Your .ttl file will be combined with the .ttl files for the other sections, as well as the base file defining the authority and document this section is from:

{starting_graph}

Now, given the following section of a building code rulebook, convert it into Turtle (.ttl) format following the ontology. Use the section number as the ID for the main section entity. Create appropriate subdivisions (chapters, articles, paragraphs, etc.) as needed. Include all relevant information such as original text (make sure all text is only used ONCE, so if the text exists in originaltext in an object like an article it shouldn't be in the originaltext of the parent section nor any child objects like members, etc.), references, and any specific measurements or conditions mentioned. Prefixes will be added afterwards automatically so ALWAYS start off with fro:Section_..., NEVER define any prefixes.

Additionally, you must now enhance the text by adding HTML links to relevant ontology concepts via the building ontology list below. When you identify terms that match concepts from the ontology, wrap them in HTML anchor tags that link to their URI definitions. For example:
- If discussing compartment areas, use: <a href="https://ontology.firebim.be/ontology/fbo#CompartmentArea">area of the compartment</a>
- For fire resistance requirements: <a href="https://ontology.firebim.be/ontology/fbo#FireResistance">fire resistance</a>

The links should be added to the originalText properties in the output TTL. Make sure to:
1. Only link to terms that actually exist in the building ontology
2. Maintain the original text's meaning and structure
3. Use the correct URIs from the ontology file(s)

Available building ontology terms for linking:
{', '.join(load_building_terms())}

Use these terms with the URI pattern: https://ontology.firebim.be/ontology/fbo#term

IMPORTANT FORMATTING RULES:
1. Always use triple quotes (\"\"\" \"\"\") for originalText properties that contain HTML links
2. Escape any quotes within HTML attributes using \\"
3. For simple text without HTML, you can use single quotes

Example format:
fro:hasOriginalText \"\"\"Text with <a href=\\"https://ontology.firebim.be/ontology/fbo#Term\\">linked term</a>\"\"\"@nl ;
"""
    prompt2 = f"""
Section number: {section_number}
Section text:
{section_text}

Here are some examples of how to convert sections to Turtle format. Note, follow the style used here as a very strong reference. Don't be afraid to nest members where necessary. IMPORTANT: the links to the ontology are not taken into account in the examples, only the original text is used. Examples:

{examples_str}
"""
    print(section_text)
    with open("pdftottl_instructions.txt", 'w', encoding='utf-8') as file:
        file.write(prompt)
    prompt = prompt + prompt2
    if float(section_number[:3]) == 0:
        with open("pdftottl_instructions_full.txt", "w", encoding="utf-8") as prompt_file:
            prompt_file.write(prompt)
    while True:
        try:
            if model_provider == "anthropic":
                message = client.messages.create(
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
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "fro:Section_" + str(section_number) +" a"
                                }
                            ]
                        }
                    ]
                )
                # Extract just the TTL content from the response
                response = message.content[0].text.strip()
            elif model_provider == "gemini":
                model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash-thinking-exp-01-21",
                    generation_config={**gemini_config, "temperature": 0},
                    system_instruction=prompt
                )
                response = model.generate_content(
                    prompt2
                )
                response = response.text.strip()
            
            # Remove any markdown code block markers that might be in the response
            response = re.sub(r'^```turtle\s*|\s*```$', '', response.strip())
            
            # Combine with prefix declarations
            full_ttl_content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix fro: <https://ontology.firebim.be/ontology/fro#> .
@base <https://ontology.firebim.be/ontology/fro> .\n\n"""

            # Only append the response if it doesn't start with "fro:Section_"
            if not response.startswith("fro:Section_"):
                full_ttl_content += response
            else:
                full_ttl_content += response.strip()
            
            print(full_ttl_content)
            break
        except Exception as e:
            print(e)
            time.sleep(5)
    return full_ttl_content

def create_and_combine_section_ttl(section_number, section_text, ontology, main_graph, examples_str, starting_graph, output_folder, first_section):
    file_name = os.path.join(output_folder, f"section_{section_number.replace('.', '_')}.ttl")
    
    if os.path.exists(file_name):
        try:
            # Try parsing the existing file into the main graph
            g_temp_load = Graph()
            g_temp_load.parse(file_name, format="turtle", publicID=FRO)
            for s, p, o in g_temp_load:
                if (s, p, o) not in main_graph:
                    main_graph.add((s, p, o))
            print(f"Loaded existing section {section_number} from file.")
            return True # Successfully loaded existing file
        except Exception as e:
            print(f"Error loading existing section {section_number}: {e}. Regenerating...")
            # Proceed to regenerate if loading failed
    
    #if section_number not in ['4_1']:
    #    print(f"Skipping section {section_number}.")
    #    return False # Keeps the code from engaging the AI.
    if False:#section_number not in ['4_2_6','4_2_6_1', '4_2_6_2', '4_2_6_3', '4_2_6_4', '4_2_6_5', '4_2_6_6', '4_2_6_7', '4_2_6_8']:
        print(f"Skipping section {section_number}.")
        return False 

    ttl_content = None
    for attempt in range(3): # Retain retry logic
        try:
            # 1. Get TTL content from LLM
            ttl_content = process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph)
            
            # 2. Parse LLM output into a temporary graph
            temp_graph = Graph()
            # Bind prefixes to the temporary graph for cleaner serialization
            temp_graph.bind("owl", OWL)
            temp_graph.bind("rdf", RDF)
            temp_graph.bind("xml", XML)
            temp_graph.bind("xsd", XSD)
            temp_graph.bind("rdfs", RDFS)
            temp_graph.bind("firebim", FRO)
            temp_graph.parse(data=ttl_content, format="turtle", publicID=FRO)

            # 3. Find articles and add version info to temp_graph for first article
            
            
            now_date_str = now.split('T')[0]
            articles_in_section = list(temp_graph.subjects(RDF.type, FRO.Article))
            
            if articles_in_section:
                print(f"Found {len(articles_in_section)} articles in section {section_number}. Adding version info to temp graph...")
                for article_uri in articles_in_section:
                    version_uri_str = f"v{current_version.replace('.', '_')}"
                    version_uri = URIRef(FRO[version_uri_str])
                    
                    # Add version triples to the temporary graph
                    temp_graph.add((article_uri, FRO.hasVersion, version_uri))
                    temp_graph.add((version_uri, RDF.type, FRO.Version))
                    temp_graph.add((version_uri, FRO.hasDate, Literal(now, datatype=XSD.dateTime)))
                    temp_graph.add((version_uri, FRO.hasVersionNumber, Literal(current_version)))
                    temp_graph.add((version_uri, FRO.hasDescription, Literal(f"Version {current_version} of the document")))

            # 4. Add all triples from the (potentially modified) temp_graph to the main_graph
            for s, p, o in temp_graph:
                 if (s, p, o) not in main_graph: 
                      main_graph.add((s,p,o))

            # 5. Save the modified temp_graph (including versioning) to the individual section file
            os.makedirs(output_folder, exist_ok=True)
            with open(file_name, 'wb') as f: 
                # Serialize the temp_graph which now includes versioning
                # rdflib handles encoding when writing to a binary stream
                temp_graph.serialize(f, format="turtle") 
            
            print(f"Successfully processed section {section_number} and saved with version info.")
            return True # Success

        except Exception as e:
            print(f"Error processing section {section_number} (Attempt {attempt + 1}): {e}")
            # Keep existing error handling and retry logic
            if ttl_content:
                 # Try to print the raw TTL content that caused the error during parsing/processing
                 print(f"Problematic raw TTL content snippet:\n{ttl_content[:500]}...") 
            else:
                 print("LLM call might have failed or produced no content.")

            # Wait before retrying, especially for potential rate limits
            if "rate limit" in str(e).lower():
                 print("Rate limit potentially exceeded... waiting longer.")
                 time.sleep(60) 
            else:
                 time.sleep(5) # Short wait for other errors

            if attempt < 2: # Adjusted to check attempt < 2 for 3 attempts total
                print("Retrying...")
                # Optionally adjust section_text for retry if needed (as in original code)
                # section_text += f"\n\nPrevious attempt failed with error: {str(e)}. Please ensure valid Turtle syntax and structure."
            else:
                print(f"Failed to process section {section_number} after 3 attempts.")
                # Optionally save the failed TTL content for debugging
                if ttl_content:
                     fail_file_name = os.path.join(output_folder, f"section_{section_number.replace('.', '_')}_FAILED.ttl")
                     with open(fail_file_name, 'w', encoding='utf-8') as f_fail:
                          f_fail.write(f"# Processing failed with error: {e}\n\n{ttl_content}")

    return False # Failed after retries

def compare_section_numbers(a, b):
    a_parts = [int(n) for n in a.split('.')]
    b_parts = [int(n) for n in b.split('.')]
    return (a_parts > b_parts) - (a_parts < b_parts)
    
def load_building_terms():
    # Load CSV files and extract first columns
    objects_df = pd.read_csv('matrixobjects_auto.csv')
    properties_df = pd.read_csv('matrixproperties_auto.csv')
    
    # Combine terms from both files
    building_terms = objects_df.iloc[:, 0].tolist() + properties_df.iloc[:, 0].tolist()
    return building_terms

def main():
    ontology = load_ontology('FireBIM_Document_Ontology_Alex.ttl')
    building_terms = load_building_terms()
    #pdf_filename = 'NIT_198_crop.pdf'
    pdf_filename = input_file
    markdown_filename = pdf_filename + '.md'
    output_folder = f"documentgraphs/{pdf_filename}"
    
    if os.path.exists(markdown_filename):
        with open(markdown_filename, 'r', encoding='utf-8') as file:
            rulebook_text = file.read()
    else:
        rulebook_text = extract_text_from_pdf(pdf_filename)
    
    sections = split_into_sections(rulebook_text)
    
    main_graph = create_initial_graph()
    
    # Create section structure
    section_numbers = [section_number for section_number, _, _ in sections]
    section_titles = [section_title for _, section_title, _ in sections]
    
    document = URIRef(FRO.RoyalDecree)
    
    # Preprocess sections to combine non-section content with previous sections
    processed_sections = []
    for i, (section_number, section_title, section_content) in enumerate(sections):
        with open(f"{output_folder}/section_{section_number.replace('.', '_')}.txt", 'w', encoding='utf-8') as file:
            file.write(section_content)
        if i == 0 or compare_section_numbers(section_number, processed_sections[-1][0]) > 0:
            processed_sections.append((section_number, section_title, section_content))
        else:
            # This is not a real section, add its content to the previous section
            prev_section_number, prev_section_title, prev_section_content = processed_sections[-1]
            combined_content = f"{prev_section_content}\n\n{section_title}\n{section_content}"
            processed_sections[-1] = (prev_section_number, prev_section_title, combined_content)
    
    sections = processed_sections
    section_numbers = [section_number for section_number, _, _ in sections]
    section_titles = [section_title for _, section_title, _ in sections]

    print(f"Number of processed sections: {len(sections)}")
    
    for i, section_number in enumerate(section_numbers):
        section_uri = URIRef(FRO['Section_' + section_number.replace('.', '_')])
        main_graph.add((section_uri, RDF.type, FRO.Section))
        main_graph.add((section_uri, FRO.hasID, Literal(section_number)))
        main_graph.add((section_uri, FRO.hasOriginalText, Literal(section_titles[i].upper())))
        
        # Link top-level sections to the document
        if '.' not in section_number:
            main_graph.add((document, FRO.hasSection, section_uri))
        
        # Link child sections to parent sections
        parts = section_number.split('.')
        if len(parts) > 1:
            parent_number = '.'.join(parts[:-1])
            parent_uri = URIRef(FRO['Section_' + parent_number.replace('.', '_')])
            main_graph.add((parent_uri, FRO.hasSection, section_uri))
    
    # Serialize the initial structure
    os.makedirs(output_folder, exist_ok=True)
    main_graph.serialize(f"{output_folder}/document.ttl", format="turtle")
    starting_graph = load_ontology(f"{output_folder}/document.ttl")
    
    # Load training examples
    training_examples = load_training_examples('trainingsamplesRuleToGraph')
    # Clean examples string generation slightly
    examples_str = "\n\n---\n\n".join([
        f"Input Text:\n{ex['input']}\n\nExpected TTL Output (fragment):\n{str(ex['output']).split('@base <https://ontology.firebim.be/ontology/fro> .', 1)[-1].strip()}" 
        for ex in training_examples
    ])
    # Add building terms to prompt context if needed by process_section_to_ttl
    building_terms_list = load_building_terms() # Load once

    # Process sections
    curNum = 0
    totalNum = len(sections)
    first_section = True
    for section_number, section_title, section_content in sections:
        curNum += 1
        section_number_underscore = section_number.replace('.', '_')
        file_name = os.path.join(output_folder, f"section_{section_number_underscore}.ttl")
        processed_bool = False
        
        if not section_content.strip():
            # Create empty section TTL for sections without content
            ttl_content = create_empty_section_ttl(section_number)
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(ttl_content)
            main_graph.parse(data=ttl_content, format="turtle", publicID=FRO)
        elif True:#section_number_underscore.startswith('4_2_6'):
            # Process sections with content through the LLM
            full_content = f"{section_title}\n{section_content}" if section_title else section_content
            processed_bool = create_and_combine_section_ttl(section_number_underscore, full_content, ontology, main_graph, examples_str, starting_graph, output_folder, first_section)
            first_section = False
        if processed_bool:
            print(f"Processed section {section_number}, nr. {curNum} / {totalNum}")
    
    main_graph.serialize(f"{output_folder}/combined_document_data_graph.ttl", format="turtle")

if __name__ == "__main__":
    main()