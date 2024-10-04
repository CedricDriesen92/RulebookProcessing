import os
import glob
import csv
from anthropic import AnthropicVertex
import time

# Initialize AnthropicVertex client
client = AnthropicVertex(region="europe-west1", project_id="neat-veld-422214-p1")

def extract_objects_properties(text_content, section_number):
    prompt = f"""
Analyze the following text from a rulebook section and extract all BIM-compatible objects and properties that are required for rule checking. The objects and properties should be relevant to IFC (Industry Foundation Classes) concepts, and be able to be mapped to it. If no immediate mapping is available, define your own.
Make sure to make sure that IFC best practices are adhered to. Always use the English definition, try to translate it as closely as possible.
Prioritize properties over objects, as it's easier to define new properties and a lot harder. Really AVOID creating new objects...
When defining new properties, use the 'firebim' property set and propose a property name.

For each object and property, provide:
1. The type of object or property (Object or Property only!)
2. The name of the object or property (in English!)
3. Its potential IFC mapping (if you can infer it, otherwise create one as discussed earlier, always starting with the property set Firebim.xxx)


Important:
- Focus only on objects and properties that are directly involved in the rule checking process.
- If you're unsure about the IFC mapping, leave it blank.
- ALWAYS provide your response in a CSV format with headers: Type,Name,IFC_Mapping

Text content:
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

def update_csv(csv_file, new_data, section_number):
    existing_data = set()
    if os.path.exists(csv_file):
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            existing_data = set((row[0], row[1]) for row in reader)

    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(['Name', 'IFC_Mapping', 'Section'])
        
        for row in csv.reader(new_data.splitlines()):
            if len(row) >= 3 and row[0] != 'Type':  # Skip header if present
                name, ifc_mapping = row[1], row[2]
                if (name, ifc_mapping) not in existing_data:
                    writer.writerow([name, ifc_mapping, section_number])
                    existing_data.add((name, ifc_mapping))

def main():
    input_folder = 'trainingsamplesRuleToGraph'
    objects_csv = 'MatrixObjects_auto.csv'
    properties_csv = 'MatrixProperties_auto.csv'

    # Create empty CSV files if they don't exist
    for csv_file in [objects_csv, properties_csv]:
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Name', 'IFC_Mapping', 'Section'])

    for txt_file in sorted(glob.glob(os.path.join(input_folder, '*.txt'))):
        base_name = os.path.splitext(os.path.basename(txt_file))[0]
        section_number = '_'.join(base_name.split('_')[:3])  # Extract section number

        with open(txt_file, 'r', encoding='utf-8') as f:
            txt_content = f.read()

        print(f"Processing {base_name}...")
        extracted_data = extract_objects_properties(txt_content, section_number)

        # Split the extracted data into objects and properties
        objects_data = "Type,Name,IFC_Mapping\n"
        properties_data = "Type,Name,IFC_Mapping\n"

        for line in extracted_data.splitlines()[1:]:  # Skip the header
            if line.startswith('Object,'):
                objects_data += line + '\n'
            elif line.startswith('Property,'):
                properties_data += line + '\n'

        update_csv(objects_csv, objects_data, section_number)
        update_csv(properties_csv, properties_data, section_number)

    print("CSV generation complete.")

if __name__ == "__main__":
    main()