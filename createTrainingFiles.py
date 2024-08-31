import os
import json

def read_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()

def generate_jsonl():
    # Read the system message from pdftottl_instructions.txt
    system_message = read_file('pdftottl_instructions.txt')

    # Get all .txt files in the trainingsamplesRuleToGraph folder
    folder_path = 'trainingsamplesRuleToGraph'
    txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]

    # Generate JSONL data
    jsonl_data = []
    for txt_file in txt_files:
        base_name = os.path.splitext(txt_file)[0]
        ttl_file = f"{base_name}.ttl"

        # Check if corresponding .ttl file exists
        if os.path.exists(os.path.join(folder_path, ttl_file)):
            user_message = read_file(os.path.join(folder_path, txt_file))
            assistant_message = read_file(os.path.join(folder_path, ttl_file))

            jsonl_entry = {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_message}
                ]
            }
            jsonl_data.append(jsonl_entry)

    # Write JSONL file
    with open('openai_training_data.jsonl', 'w', encoding='utf-8') as outfile:
        for entry in jsonl_data:
            json.dump(entry, outfile, ensure_ascii=False)
            outfile.write('\n')

    print(f"Generated JSONL file with {len(jsonl_data)} entries.")

if __name__ == "__main__":
    generate_jsonl()