import nltk
import re
from transformers import pipeline
from transformers import AutoModelForCausalLM, AutoTokenizer
from ctransformers import AutoModelForCausalLM as CTAutoModelForCausalLM
from llama_cpp import Llama
import torch
import os
from huggingface_hub import login, hf_hub_download
login(token = "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")
nltk.download('punkt_tab')

start_marker = '<s>'
end_marker = '</s>'
separator = '\n'

def create_propositions_input(text: str) -> str:
    input_sents = nltk.tokenize.sent_tokenize(text)
    propositions_input = ''
    for sent in input_sents:
        propositions_input += f'{start_marker} ' + sent + f' {end_marker}{separator}'
    propositions_input = propositions_input.strip(f'{separator}')
    return propositions_input

def process_propositions_output(text):
    pattern = re.compile(f'{re.escape(start_marker)}(.*?){re.escape(end_marker)}', re.DOTALL)
    output_grouped_strs = re.findall(pattern, text)
    predicted_grouped_propositions = []
    for grouped_str in output_grouped_strs:
        grouped_str = grouped_str.strip(separator)
        props = [x[2:] for x in grouped_str.split(separator)]
        predicted_grouped_propositions.append(props)
    return predicted_grouped_propositions


model_path = "lmstudio-community/gemma-7b-aps-it-GGUF"
model_file = "gemma-7b-aps-it-Q4_K_M.gguf"

# Download the specific model file if it doesn't exist
local_model_path = hf_hub_download(repo_id=model_path, filename=model_file)

# Use llama-cpp-python to load the model
model = Llama(model_path=local_model_path, n_ctx=2048)  # Adjust n_ctx as needed

# Remove the tokenizer initialization as it's not needed with llama-cpp-python
# tokenizer = AutoTokenizer.from_pretrained(model_path)

# Replace the generator pipeline with a custom function
def generate_text(prompt, max_tokens=4096):
    output = model(prompt, max_tokens=max_tokens)
    return output['choices'][0]['text']

# Define the base folder for the Basisnormen document
basisnormen_folder = 'documentgraphs/BasisnormenLG_cropped.pdf'

# Create the APS folder if it doesn't exist
aps_folder = os.path.join(basisnormen_folder, 'APS')
os.makedirs(aps_folder, exist_ok=True)

def save_result_to_file(file_name, result):
    output_file = os.path.join(aps_folder, f"{os.path.splitext(file_name)[0]}_aps.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        for group in result:
            f.write("Group:\n")
            for proposition in group:
                f.write(f"- {proposition}\n")
            f.write("\n")

for file in os.listdir(basisnormen_folder):
    if file.endswith('.txt'):
        passage = open(os.path.join(basisnormen_folder, file), 'r', encoding='utf-8').read()
        print(passage)
        input_text = create_propositions_input(passage)
        print(input_text)
        output = generate_text(input_text, max_tokens=4096)
        print(output)
        result = process_propositions_output(output)
        save_result_to_file(file, result)
        print(result)
