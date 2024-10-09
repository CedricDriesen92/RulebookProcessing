import os
import glob
import csv
from anthropic import AnthropicVertex
import time

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def extract_objects_properties(text_content, objects_csv, properties_csv, section_number):
    prompt = f"""
Analyze the following text from a rulebook section and extract all objects and properties that are required for rule checking. The objects and properties should be relevant to IFC (Industry Foundation Classes) concepts, and be able to be mapped to it. If no immediate mapping is available, define your own.
Make sure to make sure that IFC best practices are adhered to. Always use the English definition, try to translate it as closely as possible.
Prioritize properties over objects, as it's easier to define new properties and a lot harder. Really AVOID creating new objects...
When defining new properties, use the 'firebim' property set and propose a property name. Do not put spaces in the name of objects or properties.

For each object and property, provide:
1. The type of object or property (Object or Property only!)
2. The name of the object or property (in English!)
3. Its potential IFC mapping (if you can infer it, otherwise create one as discussed earlier, always starting with the property set Firebim.xxx)
4. For objects, define which of the properties you are writing it has and output them in a list without interfering with the csv format.


Important:
- If you're unsure about the IFC mapping, leave it blank.
- ALWAYS provide your response in a CSV format with headers: Type,Name,IFC_Mapping,Properties (containing its properties if an object, empty if a property),SectionNumber
- Try to follow IFC thought patterns, these definitions should be able to be used in any IFC environment.
- ONLY output the data, no commentary, nothing but the CSV data. Your response is not read by a human but by a dumb program.
- Be COMPLETE!!! Even if it's already defined in the output given later, define it again since the section number will be added dynamically.

This is the output of previous sections, merged. Output your data as you would without this information, except if existing objects/properties would match your definition, then use that existing name to output but with your defined IFC mapping and properties. The outputs will be merged later, so this info is given to you to avoid doubles.

objects:
{objects_csv}

properties:
{properties_csv}

This is an example output:
Type,Name,IFC_Mapping,Properties,SectionNumber
Object,Wall,IfcWall,"FireResistanceRating,Location,IsExternal",section_3_2
Object,Roof,IfcRoof,"InnerProtectionFireResistance",section_3_2
Property,FireResistanceRating,Pset_BeamCommon.FireRating,,section_3_2
Property,Location,Firebim.StructuralElementLocation,,section_3_2
Property,IsExternal,Pset_WallCommon.IsExternal,,section_3_2

Text content (your main input with section number {section_number}):
{text_content}
"""

    while True:
        try:
            response = client.messages.create(
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                model="claude-3-5-sonnet@20240620"
            )
            print(response.content[0].text.strip())
            return response.content[0].text.strip()
        except Exception as e:
            print(f"Error in LLM processing: {e}")
            time.sleep(5)


def update_csv(csv_file, new_data, section_number, is_object=False):
    existing_data = {}
    if os.path.exists(csv_file):
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['Name']
                if name not in existing_data:
                    existing_data[name] = {'IFC_Mapping': set(), 'Section': set(), 'Properties': set()}
                existing_data[name]['IFC_Mapping'].add(row['IFC_Mapping'])
                existing_data[name]['Section'].add(row['Section'])
                if is_object and 'Properties' in row:
                    existing_data[name]['Properties'].update(row['Properties'].split(','))

    for row in csv.reader(new_data.splitlines()):
        if len(row) >= 3 and row[0] != 'Type':  # Skip header if present
            name, ifc_mapping = row[1], row[2]
            properties = row[3] if is_object and len(row) > 3 else ''
            if name in existing_data:
                existing_data[name]['IFC_Mapping'].add(ifc_mapping)
                existing_data[name]['Section'].add(section_number)
                if is_object:
                    existing_data[name]['Properties'].update(properties.split(','))
            else:
                existing_data[name] = {
                    'IFC_Mapping': {ifc_mapping},
                    'Section': {section_number},
                    'Properties': set(properties.split(',')) if (is_object and properties not in ['','None']) else set()
                }

    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        headers = ['Name', 'IFC_Mapping', 'Section']
        if is_object:
            headers.append('Properties')
        writer.writerow(headers)
        for name, data in existing_data.items():
            row = [
                name,
                ','.join(sorted(data['IFC_Mapping'])),
                ','.join(sorted(data['Section']))
            ]
            if is_object:
                row.append(','.join(sorted(data['Properties'])))
            writer.writerow(row)

def main():
    input_folder = 'trainingsamplesRuleToGraph'
    objects_csv = 'MatrixObjects_auto.csv'
    properties_csv = 'MatrixProperties_auto.csv'

    # Create empty CSV files if they don't exist
    for csv_file in [objects_csv, properties_csv]:
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'IFC_Mapping', 'Section', 'Properties'] if csv_file == objects_csv else ['Name', 'IFC_Mapping', 'Section'])

    for txt_file in sorted(glob.glob(os.path.join(input_folder, '*.txt'))):
        base_name = os.path.splitext(os.path.basename(txt_file))[0]
        section_number = '_'.join(base_name.split('_'))  # Extract section number

        with open(txt_file, 'r', encoding='utf-8') as f:
            txt_content = f.read()
        # Read the entire content of the CSV files
        with open(objects_csv, 'r', encoding='utf-8') as f:
            objects_content = f.read()
        
        with open(properties_csv, 'r', encoding='utf-8') as f:
            properties_content = f.read()

        print(f"Processing {base_name}...")
        extracted_data = extract_objects_properties(txt_content, objects_content, properties_content, section_number)

        # Split the extracted data into objects and properties
        objects_data = "Type,Name,IFC_Mapping,Properties\n"
        properties_data = "Type,Name,IFC_Mapping\n"

        for line in extracted_data.splitlines()[1:]:  # Skip the header
            if line.startswith('Object,'):
                objects_data += line + '\n'
            elif line.startswith('Property,'):
                properties_data += line + '\n'

        update_csv(objects_csv, objects_data, section_number, is_object=True)
        update_csv(properties_csv, properties_data, section_number, is_object=False)

    print("CSV generation complete.")

if __name__ == "__main__":
    main()