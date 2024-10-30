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
from rdflib.namespace import RDF, RDFS, XSD
import os
import glob
import time
from llama_parse import LlamaParse
from sympy import true
from dotenv import load_dotenv

load_dotenv()

anthropic_key = os.getenv("ANTHROPIC_API_KEY")
print(anthropic_key)
#client = AnthropicVertex(region="us-east5", project_id="neat-veld-422214-p1")
#client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")
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
    text = LlamaParse(result_type="markdown", skip_diagonal_text=true, show_progress=true, parsing_instruction="Extract the text from the document in Markdown format, make sure all titles for sections/subsections/subsubsections keep their numbering").load_data(pdf_path)
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
@prefix firebim: <http://example.com/firebim#> .
@base <http://example.com/firebim> .

firebim:Section_{section_number.replace('.', '_')} a firebim:Section ;
    firebim:hasID "{section_number}" .
"""
    return ttl_content

FIREBIM = Namespace("http://example.com/firebim#")

def create_initial_graph():
    g = Graph()
    g.bind("firebim", FIREBIM)
    
    document = URIRef(FIREBIM.RoyalDecree)
    authority = URIRef(FIREBIM.Belgian_Government)
    
    g.add((document, RDF.type, FIREBIM.Document))
    g.add((document, FIREBIM.hasID, Literal("RoyalDecree1994")))
    g.add((document, FIREBIM.issued, Literal("1994-07-07", datatype=XSD.date)))
    
    g.add((authority, RDF.type, FIREBIM.Authority))
    g.add((authority, FIREBIM.hasDocument, document))
    
    return g

def process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph):
    prompt = f"""
You are tasked with converting building code rulebook sections into Turtle (.ttl) format following the FireBIM Document Ontology. Here's the complete ontology for your reference:

{ontology}
Here is some more info on the firebim ontology and how you should use it:

The firebim regulation ontology maps one-to-one to parts of the AEC3PO ontology, however, it is more lightweight, following best practices from the W3C Linked Building Data Community Group. It consists of three main classes, the firebim:Authority (which represents the legal body that publishes and maintains the regulatory document), the firebim:DocumentSubdivision (which represents documents or parts of documents), and the firebim:Reference (which represents references to other representations of the regulation, or similar regulations). The firebim:DocumentSubdivision class has a subclass tree that defines a document, a section, an article, and a member. The latter typically holds the one or multiple bodies of text that an article exists of. We introduce multiple types of sections, such as chapters, subchapters, paragraphs, appendices, tables, and figures.
The created data graph should be modeled as a tree structure with multiple members per article and multiple articles per paragraph. Members can contain submembers, or they can have references to other members, using the firebim:hasBackwardReference and firebim:hasForwardReference object properties. This enables members to refer to other members if they for example contain constraints for the other member, as could be seen in Figure 2. This first part of the FireBIM ontology stack does not semantically enrich the regulation or the building itself; the regulatory member text is simply added to the graph as a literal.

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

Now, given the following section of a building code rulebook, convert it into Turtle (.ttl) format following this ontology. Use the section number as the ID for the main section entity. Create appropriate subdivisions (chapters, articles, paragraphs, etc.) as needed. Include all relevant information such as original text (make sure all text is only used ONCE, so if the text exists in originaltext in an object like an article it shouldn't be in the originaltext of the parent section nor any child objects like members, etc.), references, and any specific measurements or conditions mentioned.
"""
    prompt2 = f"""
Section number: {section_number}
Section text:
{section_text}

Here are some examples of how to convert sections to Turtle format. Note, follow the style used here as a very strong reference. Don't be afraid to nest members where necessary. Examples:

{examples_str}
"""
    with open("pdftottl_instructions.txt", 'w', encoding='utf-8') as file:
        file.write(prompt)
    prompt = prompt + prompt2
    if float(section_number[:3]) == 0:
        with open("pdftottl_instructions_full.txt", "w", encoding="utf-8") as prompt_file:
            prompt_file.write(prompt)
    while True:
        try:
            # response = client.messages.create(
            #     max_tokens=8000,
            #     messages=[
            #         {"role": "user", "content": prompt},
            #         {"role": "assistant", "content": "firebim:Section_" + str(section_number) +" a"}
            #     ],
            #     model="claude-3-5-sonnet-v2@20241022"
            # )
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
                                "text": "firebim:Section_" + str(section_number) +" a"
                            }
                        ]
                    }
                ]
            )
            response = message.content[0].text
            print(response)
            break
        except Exception as e:
            print(e)
            time.sleep(5)
    full_ttl_content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix firebim: <http://example.com/firebim#> .
@base <http://example.com/firebim> .\n\n"""
    full_ttl_content += "firebim:Section_" + str(section_number) +" a " + response.strip()
    return full_ttl_content

def create_and_combine_section_ttl(section_number, section_text, ontology, main_graph, examples_str, starting_graph, output_folder):
    file_name = os.path.join(output_folder, f"section_{section_number.replace('.', '_')}.ttl")
    
    if os.path.exists(file_name):
        try:
            main_graph.parse(file_name, format="turtle", publicID=FIREBIM)
            return True
        except Exception as e:
            print(f"Error loading existing section {section_number}: {e}")
    
    if section_number not in ['4_1']:
        print(f"Skipping section {section_number}.")
        return False # Keeps the code from engaging the AI.
    for attempt in range(3):
        try:
            ttl_content = process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph)
            main_graph.parse(data=ttl_content, format="turtle", publicID=FIREBIM)
            
            os.makedirs(output_folder, exist_ok=True)
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(ttl_content)
            
            return True
        except Exception as e:
            print(f"Error processing section {section_number} (Attempt {attempt + 1}): {e}")
            if ttl_content:
                print(f"Generated TTL content:\n{ttl_content}")
            else:
                print("probably rate limit exceeded... waiting")
                time.sleep(5)
            if attempt < 3:
                print("Retrying with AI...")
                section_text += f"\n\nPrevious attempt failed with error: {str(e)}. Please try again and ensure valid Turtle syntax."
            else:
                print(f"Failed to process section {section_number} after 6 attempts")
    
    return False

def compare_section_numbers(a, b):
    a_parts = [int(n) for n in a.split('.')]
    b_parts = [int(n) for n in b.split('.')]
    return (a_parts > b_parts) - (a_parts < b_parts)
    
def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    #pdf_filename = 'NIT_198_crop.pdf'
    pdf_filename = 'BasisnormenLG_cropped.pdf'
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
    
    document = URIRef(FIREBIM.RoyalDecree)
    
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
        section_uri = URIRef(FIREBIM['Section_' + section_number.replace('.', '_')])
        main_graph.add((section_uri, RDF.type, FIREBIM.Section))
        main_graph.add((section_uri, FIREBIM.hasID, Literal(section_number)))
        main_graph.add((section_uri, FIREBIM.hasOriginalText, Literal(section_titles[i].upper())))
        
        # Link top-level sections to the document
        if '.' not in section_number:
            main_graph.add((document, FIREBIM.hasSection, section_uri))
        
        # Link child sections to parent sections
        parts = section_number.split('.')
        if len(parts) > 1:
            parent_number = '.'.join(parts[:-1])
            parent_uri = URIRef(FIREBIM['Section_' + parent_number.replace('.', '_')])
            main_graph.add((parent_uri, FIREBIM.hasSection, section_uri))
    
    # Serialize the initial structure
    os.makedirs(output_folder, exist_ok=True)
    main_graph.serialize(f"{output_folder}/document.ttl", format="turtle")
    starting_graph = load_ontology(f"{output_folder}/document.ttl")
    
    # Load training examples
    training_examples = load_training_examples('trainingsamplesRuleToGraph')
    examples_str = "\n\n".join([f"Input:\n{ex['input']}\n\nExpected output:\n{str(ex['output']).split('@base <http://example.com/firebim> .\n\n', 1)[-1]}\n" for ex in training_examples])
    
    # Process sections
    curNum = 0
    totalNum = len(sections)
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
            main_graph.parse(data=ttl_content, format="turtle", publicID=FIREBIM)
        else:
            # Process sections with content through the LLM
            full_content = f"{section_title}\n{section_content}" if section_title else section_content
            processed_bool = create_and_combine_section_ttl(section_number_underscore, full_content, ontology, main_graph, examples_str, starting_graph, output_folder)
        
        if processed_bool:
            print(f"Processed section {section_number}, nr. {curNum} / {totalNum}")
    
    main_graph.serialize(f"{output_folder}/combined_document_data_graph.ttl", format="turtle")

if __name__ == "__main__":
    main()