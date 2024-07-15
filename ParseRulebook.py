import PyPDF2
import rdflib
import json
from anthropic import AnthropicVertex
from typing import List, Dict
import re
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD
import os

client = AnthropicVertex(region="europe-west1", project_id="spatial-conduit-420822", )

def extract_text_from_pdf(pdf_path: str) -> str:
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def split_into_sections(text):
    # Looks for section headers like "0 GENERAL", "1 IMPLANTATION AND ACCESS ROADS", etc.
    pattern = r'\n(?=\d+(?:\.\d+)*\s+[A-Z][A-Z\s]+)'
    sections = re.split(pattern, text)
    
    # Remove any empty sections and strip whitespace
    sections = [section.strip() for section in sections if section.strip()]
    
    # Further split subsections
    detailed_sections = []
    for section in sections:
        subsections = re.split(r'\n(?=\d+\.\d+\s+)', section)
        detailed_sections.extend(subsections)
    
    return detailed_sections

def process_section(parnum, totparnum, section):
    prompt = """
    Analyze the following building code rulebook text and extract individual rules.
    For each rule, provide:
    1. Rule ID
    2. Entities involved (e.g., rooms, doors, walls)
    3. Conditions or constraints
    4. Measurements or thresholds
    5. Relationships between entities

    Provide the output as a JSON array of rule objects. Make sure every rule is separate and clear. If there are no explicit or implicit rules to parse, simply output a valid 1-line json with "rules": "No rules" in it. Your output will be sent directly to a json processor so it's important you only output valid json.
    
    Here is an example of an output, follow this format as much as possible. Replace 'LG-xxx' by the section/subsection/paragraph you are in if available, whichever is most detailed, otherwise use LG-""" +str(parnum)+""".
    {
  "rules": [
    {
      "Rule ID": "LG-001",
      "Entities": ["compartment", "building", "floor"],
      "Conditions": [
        "Applies to buildings with more than one floor",
        "Exception for parking buildings"
      ],
      "Measurements": [
        {"type": "maximum area", "value": 2500, "unit": "m²"}
      ],
      "Relationships": [
        "Compartment is part of building",
        "Compartment may span multiple floors if conditions met"
      ]
    },
    {
      "Rule ID": "LG-002",
      "Entities": ["single-story building", "compartment"],
      "Conditions": [
        "Applies to single-story buildings only"
      ],
      "Measurements": [
        {"type": "maximum area", "value": 3500, "unit": "m²"},
        {"type": "maximum length", "value": 90, "unit": "m"}
      ],
      "Relationships": [
        "Compartment is part of single-story building"
      ]
    },
    {
      "Rule ID": "LG-003",
      "Entities": ["fire department vehicle", "building facade", "access road"],
      "Conditions": [
        "Applies to single-story buildings",
        "Access road can be public highway or special access road"
      ],
      "Measurements": [
        {"type": "maximum approach distance", "value": 60, "unit": "m"},
        {"type": "minimum road width", "value": 4, "unit": "m"},
        {"type": "minimum inner turning radius", "value": 11, "unit": "m"},
        {"type": "minimum outer turning radius", "value": 15, "unit": "m"},
        {"type": "minimum clear height", "value": 4, "unit": "m"},
        {"type": "maximum slope", "value": 6, "unit": "%"}
      ],
      "Relationships": [
        "Fire department vehicle must be able to approach building facade",
        "Access road provides path for fire department vehicle"
      ]
    },
    {
      "Rule ID": "LG-004",
      "Entities": ["evacuation route", "staircase", "exit"],
      "Conditions": [
        "Applies to compartments with daytime occupancy only"
      ],
      "Measurements": [
        {"type": "maximum distance to evacuation route", "value": 30, "unit": "m"},
        {"type": "maximum distance to nearest staircase/exit", "value": 45, "unit": "m"},
        {"type": "maximum distance to second staircase/exit", "value": 80, "unit": "m"}
      ],
      "Relationships": [
        "Evacuation route connects to staircases and exits",
        "Compartment contains evacuation routes"
      ]
    }
  ]
}
    """
    ruletext_as_message = [{
        "role": "user",
        "content": section
    },
    {
        "role": "assistant",
        "content": "{"
    }]
    response = client.messages.create(
        max_tokens=2048,
        messages=ruletext_as_message,
        model="claude-3-5-sonnet@20240620",
        system=prompt
    )
    
    response_text = "{\n" + response.content[0].text
   
    answer = response_text

    print("Paragraph " + str(parnum) + " out of " + str(totparnum)+": ")
    print(answer)
    
    return json.loads(answer)

def combine_processed_sections(processed_sections):
    all_rules = []
    for section_rules in processed_sections:
        if "no rules" not in section_rules.lower():
            all_rules.extend(section_rules)
    
    # Ensure unique Rule IDs
    used_ids = set()
    for rule in all_rules:
        while rule['Rule ID'] in used_ids:
            rule['Rule ID'] += '_dup'
        used_ids.add(rule['Rule ID'])
    
    return all_rules

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

    In your .ttl, make sure to give the royal decree document a hasSection link to this section. Make sure the article originaltext has the full text, including text that defines the members. Adding all originaltext from all articles should recreate the rules part of the document.
    Do not include prefix declarations or @base. Start directly with the triples for this section. Ensure the output is valid Turtle syntax that can be parsed when added to an existing graph.

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

    response = client.messages.create(
        max_tokens=4096,
        messages=[
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "firebim:Section_" + str(section_number) +" a"}
        ],
        model="claude-3-5-sonnet@20240620"
    )
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
            section_graph.parse(file_name, format="turtle")
            main_graph += section_graph
            print(f"Loaded existing section {section_number}")
            return True
        except Exception as e:
            print(f"Error loading existing section {section_number}: {e}")
    
    for attempt in range(3):
        try:
            ttl_content = process_section_to_ttl(section_number, section_text, ontology)
            section_graph = Graph()
            section_graph.parse(data=ttl_content, format="turtle", publicID=FIREBIM)
            main_graph += section_graph
            
            os.makedirs("sections", exist_ok=True)
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(ttl_content)
            
            print(f"Processed section {section_number} (Attempt {attempt + 1})")
            return True
        except Exception as e:
            print(f"Error processing section {section_number} (Attempt {attempt + 1}): {e}")
            print(f"Generated TTL content:\n{ttl_content}")
            if attempt < 2:
                print("Retrying with AI...")
                # Here we're giving feedback to the AI about the error
                section_text += f"\n\nPrevious attempt failed with error: {str(e)}. Please try again and ensure valid Turtle syntax."
            else:
                print(f"Failed to process section {section_number} after 3 attempts")
    
    return False

def main():
    ontology = load_ontology('FireBIM_Document_Ontology.ttl')
    rulebook_text = extract_text_from_pdf('BE_BasisnormenLG_EN_excerpt.pdf')
    sections = split_into_sections(rulebook_text)
    if not os.path.isfile("sections/document.ttl"):
        main_graph = create_initial_graph()
        main_graph.serialize("sections/document.ttl", format="turtle")
    else:
        main_graph = Graph()
        main_graph.parse("sections/document.ttl", format="turtle")
    
    for i, section in enumerate(sections):#[:10]):  # Process first 10 sections for testing
        match = re.match(r'(\d+(?:\.\d+)*)\s', section)
        if match:
            section_number = match.group(1)
        else:
            section_number = str(i+1)
        
        create_and_combine_section_ttl(section_number, section, ontology, main_graph)
    
    main_graph.serialize("combined_document_data_graph.ttl", format="turtle")

if __name__ == "__main__":
    main()