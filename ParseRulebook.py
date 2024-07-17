import pypdf
import rdflib
import json
from anthropic import AnthropicVertex
from typing import List, Dict
import re
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD
import os
import time

client = AnthropicVertex(region="europe-west1", project_id="spatial-conduit-420822", )

def extract_text_from_pdf(pdf_path: str) -> str:
    with open(pdf_path, 'rb') as file:
        reader = pypdf.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) + "\n"
    return text

def split_into_sections(text):
    # Looks for main section headers like "0 GENERAL", "1 IMPLANTATION AND ACCESS ROADS", etc.
    main_pattern = r'\n(?=\d+(?:\.\d+)*\s+[A-Z][A-Z\s]+)'
    main_sections = re.split(main_pattern, text)
    
    # Remove any empty sections and strip whitespace
    main_sections = [section.strip() for section in main_sections if section.strip()]
    
    detailed_sections = []
    for main_section in main_sections:
        # Split into subsections
        subsection_pattern = r'\n(?=\d+\.\d+\s+)'
        subsections = re.split(subsection_pattern, main_section)
        
        for subsection in subsections:
            # Split into subsubsections
            subsubsection_pattern = r'\n(?=\d+\.\d+\.\d+\s+)'
            subsubsections = re.split(subsubsection_pattern, subsection)
            
            detailed_sections.extend(subsubsections)
    
    # Further clean up and identify sections
    final_sections = []
    for section in detailed_sections:
        match = re.match(r'(\d+(?:\.\d+)*)\s+(.*?)(?:\n|$)', section)
        if match:
            section_number = match.group(1)
            section_title = match.group(2)
            section_content = section[match.end():].strip()
            final_sections.append((section_number, section_title, section_content))
        else:
            # If no match, it might be content continuing from the previous section
            final_sections.append((None, None, section.strip()))
    
    return final_sections

def prepare_shacl_generation(mapped_rules: List[Dict]) -> List[Dict]:
    prepared_rules = []
    
    for rule in mapped_rules:
        prompt = f"""
        Prepare the given rule for SHACL shape generation:

        Provide:
        1. The main target class for the shape
        2. The properties to be constrained
        3. The type of constraint for each property (e.g., minCount, maxCount, hasValue)
        4. Any complex logic that might require SHACL-SPARQL or SHACL-JS
        5. Suggested error message for violations

        Output the result as a JSON object.
        """
        
        rule_as_message = {
            "role": "user",
            "content": json.dumps(rule)
        }
        response = client.messages.create(
            max_tokens=2048,
            messages=rule_as_message,
            model="claude-3-5-sonnet@20240620",
            system=prompt
        )
        
        shacl_prep =  json.loads(response.content[0].text)
        rule['shacl_preparation'] = shacl_prep
        prepared_rules.append(rule)
    
    return prepared_rules

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

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

def load_ontology(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def process_section_to_ttl(section_number, section_text, ontology):
    prompt = f"""
    You are an AI assistant specialized in converting building code rulebook sections into Turtle (.ttl) format following the FireBIM Document Ontology. Here's the complete ontology for your reference:

    {ontology}
    Here is some more info on the firebim ontology and how you should use it:
    
    The firebim regulation ontology maps one-to-one to parts of the AEC3PO ontology, however, it is more lightweight, following best practices from the W3C Linked Building Data Community Group. It consists of three main classes, the firebim:Authority (which represents the legal body that publishes and maintains the regulatory document), the firebim:DocumentSubdivision (which represents documents or parts of documents), and the firebim:Reference (which represents references to other representations of the regulation, or similar regulations). The firebim:DocumentSubdivision class has a subclass tree that defines a document, a section, an article, and a member. The latter typically holds the one or multiple bodies of text that an article exists of. We introduce multiple types of sections, such as chapters, subchapters, paragraphs, appendices, tables, and figures.
    The created data graph (not shown here) clearly shows how a document is modeled as a tree structure with multiple members per article and multiple articles per paragraph. Members can have references to other members, using the firebim:hasBackwardReference and firebim:hasForwardReference object properties. This enables members to refer to other members if they for example contain constraints for the other member, as could be seen in Figure 2. This first part of the FireBIM ontology stack does not semantically enrich the regulation or the building itself; the regulatory member text is simply added to the graph as a literal.
    
    Now, given the following section of a building code rulebook, convert it into Turtle (.ttl) format following this ontology. Use the section number as the ID for the main section entity. Create appropriate subdivisions (chapters, articles, paragraphs, etc.) as needed. Include all relevant information such as original text, references, and any specific measurements or conditions mentioned.

    Section number: {section_number}
    Section text:
    {section_text}

    In your .ttl, make sure to give the royal decree document a hasSection link to this section. Make sure the article originaltext has the full text, including text that defines the members. Adding all originaltext from all articles should recreate the rules part of the document. For the section don't include the full originaltext, only the part preceding the articles themselves.
    Do not include prefix declarations or @base. Start directly with the triples for this section. Ensure the output is valid Turtle syntax that can be parsed when added to an existing graph.
    Depending on the language of the source text, make sure to add language tags where necessary. Do not translate the original text in any way, keep the source perfectly accurate.
    If a figure or table is implied in the text, make sure to declare it and add the required relations/properties. Even if you can't see it, it's still there.
    Make sure every article consists of AT LEAST 1 member, these are the rule building blocks. However, does not necessarily need an article, since articles are about rules and checks and requirements. 
    For text spanning multiple lines make sure to use triple quotes, as single codes will be invalid there.
    Output only the Turtle (.ttl) content, no explanations. Your .ttl file will be combined with the .ttl files for the other sections, as well as the base file defining the authority and document this section is from:
    
@prefix firebim: <http://example.com/firebim#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

firebim:Belgian_Government a firebim:Authority ;
    firebim:hasDocument firebim:RoyalDecree .

firebim:RoyalDecree a firebim:Document ;
    firebim:hasID "RoyalDecree1994" ;
    firebim:issued "1994-07-07"^^xsd:date .
    """
    while True:
        try:
            response = client.messages.create(
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "firebim:Section_" + str(section_number) +" a"}
                ],
                model="claude-3-5-sonnet@20240620"
            )
            break
        except Exception as e:
            print(e)
    full_ttl_content = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix firebim: <http://example.com/firebim#> .
@base <http://example.com/firebim> .\n\n"""
    full_ttl_content += "firebim:Section_" + str(section_number) +" a " + response.content[0].text.strip()
    return full_ttl_content

def create_and_combine_section_ttl(section_number, section_text, ontology, main_graph):
    file_name = f"sections/section_{section_number.replace('.', '_')}.ttl"
    
    if os.path.exists(file_name):
        try:
            section_graph = Graph()
            main_graph.parse(file_name, format="turtle", publicID=FIREBIM)
            #main_graph += section_graph
            print(f"Loaded existing section {section_number}")
            return True
        except Exception as e:
            print(f"Error loading existing section {section_number}: {e}")
    
    for attempt in range(3):
        try:
            ttl_content = process_section_to_ttl(section_number, section_text, ontology)
            section_graph = Graph()
            main_graph.parse(data=ttl_content, format="turtle", publicID=FIREBIM)
            
            # Update existing section in main_graph instead of adding a new one
            #section_uri = URIRef(FIREBIM['Section_' + section_number])
            #for s, p, o in section_graph.triples((section_uri, None, None)):
            #    main_graph.add((s, p, o))
            #main_graph += section_graph
            
            os.makedirs("sections", exist_ok=True)
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(ttl_content)
            
            print(f"Processed section {section_number} (Attempt {attempt + 1})")
            return True
        except Exception as e:
            print(f"Error processing section {section_number} (Attempt {attempt + 1}): {e}")
            if ttl_content:
                print(f"Generated TTL content:\n{ttl_content}")
            else:
                print("probably rate limit exceeded... waiting")
                time.sleep(5)
            if attempt < 5:
                print("Retrying with AI...")
                section_text += f"\n\nPrevious attempt failed with error: {str(e)}. Please try again and ensure valid Turtle syntax."
            else:
                print(f"Failed to process section {section_number} after 6 attempts")
    
    return False

def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    rulebook_text = extract_text_from_pdf('BasisnormenLG.pdf')
    sections = split_into_sections(rulebook_text)
    
    main_graph = create_initial_graph()
    
    # Create section structure
    section_numbers = []
    for section_number, section_title, section_content in sections:
        if section_number is not None:
            section_numbers.append(section_number.replace('.', '_'))
    
    document = URIRef(FIREBIM.RoyalDecree)
    
    # Sort section numbers to ensure parent sections are created before child sections
    section_numbers.sort(key=lambda x: [int(n) for n in x.split('_')])
    
    for section_number in section_numbers:
        section_uri = URIRef(FIREBIM['Section_' + section_number])
        main_graph.add((section_uri, RDF.type, FIREBIM.Section))
        main_graph.add((section_uri, FIREBIM.hasID, Literal(section_number.replace('_', '.'))))
        
        # Link top-level sections to the document
        if '_' not in section_number:
            main_graph.add((document, FIREBIM.hasSection, section_uri))
        
        # Link child sections to parent sections
        parts = section_number.split('_')
        if len(parts) > 1:
            parent_number = '_'.join(parts[:-1])
            parent_uri = URIRef(FIREBIM['Section_' + parent_number])
            main_graph.add((parent_uri, FIREBIM.hasSection, section_uri))
    
    # Serialize the initial structure
    main_graph.serialize("sections/document.ttl", format="turtle")
    
    # Process sections
    for section_number, section_title, section_content in sections:
        if section_number is not None:
            section_number_underscore = section_number.replace('.', '_')
            #print(float(section_number[:3]))
            if -1 < float(section_number[:3]) < 3.5:
                full_content = f"{section_title}\n{section_content}" if section_title else section_content
                create_and_combine_section_ttl(section_number_underscore, full_content, ontology, main_graph)
    
    main_graph.serialize("combined_document_data_graph.ttl", format="turtle")

if __name__ == "__main__":
    main()