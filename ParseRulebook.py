import PyPDF2
import rdflib
import json
from anthropic import AnthropicVertex
from typing import List, Dict
import re

client = AnthropicVertex(region="europe-west1", project_id="spatial-conduit-420822", )

def extract_text_from_pdf(pdf_path: str) -> str:
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def split_into_sections(text):
    # This regex pattern looks for section headers like "0 GENERAL", "1 IMPLANTATION AND ACCESS ROADS", etc.
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

def parse_ontology(ttl_path: str) -> Dict:
    g = rdflib.Graph()
    g.parse(ttl_path, format="turtle")
    
    ontology = {
        "classes": [],
        "properties": [],
        "relationships": []
    }
    
    for s, p, o in g:
        if p == rdflib.RDF.type:
            if o == rdflib.OWL.Class:
                ontology["classes"].append(str(s))
            elif o == rdflib.OWL.ObjectProperty or o == rdflib.OWL.DatatypeProperty:
                ontology["properties"].append(str(s))
        elif p == rdflib.RDFS.subClassOf:
            ontology["relationships"].append((str(s), "subClassOf", str(o)))
    
    return ontology


def map_to_ontology(processed_rules: List[Dict], ontology: Dict) -> List[Dict]:
    mapped_rules = []
    
    for rule in processed_rules:
        prompt = f"""
        Map the given rule entities to the provided ontology:

        Ontology:
        Classes: {ontology['classes']}
        Properties: {ontology['properties']}
        Relationships: {ontology['relationships']}

        Provide the mapping as a JSON object with keys for each entity in the rule
        and values from the ontology. If no exact match is found, suggest the closest match.
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
        
        mapping =  json.loads(response.content[0].text)
        rule['ontology_mapping'] = mapping
        mapped_rules.append(rule)
    
    return mapped_rules


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


rulebook_text = extract_text_from_pdf('BE_BasisnormenLG_EN_excerpt.pdf')
sections = split_into_sections(rulebook_text)
processed_sections = []
intermediate_rules_file = open("intermediate_rules.txt", "w")
for i, section in enumerate(sections):
    if i >= 0: #Skip initial paragraphs
        try:
            cur_processed_section = process_section(i, len(sections), section)
            processed_sections.append(cur_processed_section)

            # Create a copy of cur_processed_section and add the FullText to it
            output_dict = cur_processed_section.copy()
            output_dict["FullText"] = section
            
            intermediate_rules_file.write(json.dumps(output_dict, indent=1) + "\n")
            intermediate_rules_file.flush()
        except Exception as error:
            print("Error: " + str(error))
combined_rules = combine_processed_sections(processed_sections)
with open('processed_rules.json', 'w') as f:
    json.dump(combined_rules, f, indent=2)

#ontology = parse_ontology('building_ontology.ttl')
#ontology_mapped_rules = map_to_ontology(processed_rules, ontology)
#shacl_prepared_rules = prepare_shacl_generation(ontology_mapped_rules)

#with open('processed_rules.json', 'w') as f:
#    json.dump(shacl_prepared_rules, f, indent=2)