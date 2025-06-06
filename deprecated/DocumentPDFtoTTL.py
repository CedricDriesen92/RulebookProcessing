import pypdf
import pymupdf
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
import rdflib
import json
from anthropic import AnthropicVertex
from typing import List, Dict
import re
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD
import os
import glob
import time
from llama_parse import LlamaParse

os.environ["LLAMA_CLOUD_API_KEY"] = "llx-SbQRnu1gMsOiKK7KKS12D9bV3Ccvc2xZ6a7YauCOycd4YmK1"
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def load_ontology(file_path):
    with open(file_path, 'r') as file:
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
    text = LlamaParse(result_type="text").load_data(pdf_path)
    print(text[0].text[:1000])
    return text

def split_into_sections(text):
    # Pattern for sections: number(s) followed by any amount of spaces and a word
    section_pattern = r'\n(?=(?:\d+\.)*\d+\s+\S)'
    sections = re.split(section_pattern, text)
    
    # Remove any empty sections and strip whitespace
    sections = [section.strip() for section in sections if section.strip()]
    
    print("Initial sections:", [s[:50] + "..." for s in sections])
    print("Number of sections found:", len(sections))
    
    final_sections = []
    current_main_section = None
    current_subsection = None
    
    for section in sections:
        # Try to match section number and title
        match = re.match(r'((?:\d+\.)*\d+)\s+(.*?)(?:\n|$)', section, re.DOTALL)
        if match:
            section_number = match.group(1)
            section_title = match.group(2).strip()
            section_content = section[match.end():].strip()
            
            # Determine the section level
            level = section_number.count('.') + 1
            
            if level == 1:
                current_main_section = section_number
                current_subsection = None
            elif level == 2:
                current_subsection = section_number
            
            # Add the section to final_sections
            final_sections.append((section_number, section_title, section_content))
            print(f"Matched section: {section_number} - {section_title[:30]}...")
        else:
            # If no match, it's likely content continuing from the previous section
            if final_sections:
                prev_number, prev_title, prev_content = final_sections[-1]
                final_sections[-1] = (prev_number, prev_title, prev_content + "\n" + section.strip())
                print(f"Appended content to previous section: {prev_number}")
            else:
                # If it's the first section and doesn't match the pattern, add it as is
                final_sections.append((None, None, section.strip()))
                print("Added unmatched content as first section")
    
    print("Final sections:", final_sections)
    return final_sections

FRO = Namespace("https://ontology.firebim.be/ontology/fro#")

def create_initial_graph():
    g = Graph()
    g.bind("firebim", FRO)
    
    document = URIRef(FRO.RoyalDecree)
    authority = URIRef(FRO.Belgian_Government)
    
    g.add((document, RDF.type, FRO.Document))
    g.add((document, FRO.hasID, Literal("RoyalDecree1994")))
    g.add((document, FRO.issued, Literal("1994-07-07", datatype=XSD.date)))
    
    g.add((authority, RDF.type, FRO.Authority))
    g.add((authority, FRO.hasDocument, document))
    
    return g

def process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph):
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
            response = client.messages.create(
                max_tokens=8000,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "fro:Section_" + str(section_number) +" a"}
                ],
                model="claude-3-5-sonnet-v2@20241022"
            )
            break
        except Exception as e:
            print(e)
            time.sleep(5)
    full_ttl_content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix fro: <https://ontology.firebim.be/ontology/fro#> .
@base <https://ontology.firebim.be/ontology/fro> .\n\n"""
    full_ttl_content += "fro:Section_" + str(section_number) +" a " + response.content[0].text.strip()
    return full_ttl_content

def create_and_combine_section_ttl(section_number, section_text, ontology, main_graph, examples_str, starting_graph, output_folder):
    file_name = os.path.join(output_folder, f"section_{section_number.replace('.', '_')}.ttl")
    
    if os.path.exists(file_name):
        try:
            main_graph.parse(file_name, format="turtle", publicID=FRO)
            return True
        except Exception as e:
            print(f"Error loading existing section {section_number}: {e}")
    
    #return False # Keeps the code from engaging the AI.
    for attempt in range(3):
        try:
            ttl_content = process_section_to_ttl(section_number, section_text, ontology, examples_str, starting_graph)
            main_graph.parse(data=ttl_content, format="turtle", publicID=FRO)
            
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

def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    pdf_filename = 'NIT_198.pdf'#'BasisnormenLG_cropped.pdf'
    rulebook_text = extract_text_from_pdf(pdf_filename)
    sections = split_into_sections(rulebook_text)
    
    main_graph = create_initial_graph()
    
    # Create section structure
    section_numbers = []
    for section_number, section_title, section_content in sections:
        if section_number is not None:
            section_numbers.append(section_number.replace('.', '_'))
            txt_file_name = f"trainingsamplesRuleToGraph/section_{section_number.replace('.', '_')}.txt"
            if not os.path.exists(txt_file_name):
                with open(txt_file_name, 'w', encoding='utf-8') as f:
                    f.write(f"Section number: {section_number}\nSection text:\n{section_content}")
    training_examples = load_training_examples('trainingsamplesRuleToGraph')
    examples_str = "\n\n".join([f"Input:\n{ex['input']}\n\nExpected output:\n{str(ex['output']).split("@base <https://ontology.firebim.be/ontology/fro> .\n\n", 1)[-1]}\n" for ex in training_examples])
    with open("current_training_total.txt", "w", encoding="utf-8") as f:
        f.write(examples_str)
    
    document = URIRef(FRO.RoyalDecree)
    
    # Sort section numbers to ensure parent sections are created before child sections
    section_numbers.sort(key=lambda x: [int(n) for n in x.split('_')])
    
    for section_number in section_numbers:
        section_uri = URIRef(FRO['Section_' + section_number])
        main_graph.add((section_uri, RDF.type, FRO.Section))
        main_graph.add((section_uri, FRO.hasID, Literal(section_number.replace('_', '.'))))
        
        # Link top-level sections to the document
        if '_' not in section_number:
            main_graph.add((document, FRO.hasSection, section_uri))
        
        # Link child sections to parent sections
        parts = section_number.split('_')
        if len(parts) > 1:
            parent_number = '_'.join(parts[:-1])
            parent_uri = URIRef(FRO['Section_' + parent_number])
            main_graph.add((parent_uri, FRO.hasSection, section_uri))
    
    # Serialize the initial structure
    output_folder = f"documentgraphs/{os.path.splitext(pdf_filename)[0]}"
    os.makedirs(output_folder, exist_ok=True)
    main_graph.serialize(f"{output_folder}/document.ttl", format="turtle")
    starting_graph = load_ontology(f"{output_folder}/document.ttl")
    
    # Process sections
    curNum = 0
    totalNum = len(sections)
    for section_number, section_title, section_content in sections:
        curNum += 1
        if section_number is not None:
            section_number_underscore = section_number.replace('.', '_')
            if -1 < float(section_number[:3]) < 60:
                full_content = f"{section_title}\n{section_content}" if section_title else section_content
                create_and_combine_section_ttl(section_number_underscore, full_content, ontology, main_graph, examples_str, starting_graph, output_folder)
                print("Processed section "+str(section_number) + ", nr. " + str(curNum) + " / " + str(totalNum))
    
    main_graph.serialize("combined_document_data_graph.ttl", format="turtle")
if __name__ == "__main__":
    main()