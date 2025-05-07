import os
import glob
import json
import re
import time
from dotenv import load_dotenv
import google.generativeai as genai
from rdflib import Graph, Literal, URIRef, Namespace
from rdflib.namespace import RDF, RDFS, DCTERMS

# Load environment variables
load_dotenv()

# --- Configuration ---

google_key = os.getenv("GEMINI_API_KEY")
input_file_base = os.getenv("INPUT_FILE")
if not input_file_base:
    raise ValueError("INPUT_FILE environment variable not set.")

# Define base directories based on input file
doc_graph_dir = f"documentgraphs/{input_file_base}"
# No RASE output needed
shacl_output_dir = f"SHACL/{input_file_base}" # Or a single file like f"SHACL/{input_file_base}.shacl.ttl"
shacl_docs_path = "SHACLdocs.txt" # Path to the SHACL documentation file

# Ensure output directory exists
os.makedirs(shacl_output_dir, exist_ok=True)

# --- Gemini Model Setup ---

if not google_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

genai.configure(api_key=google_key)

# Configure the Gemini model
gemini_config = {
    "temperature": 0.5, # Lower temperature for more deterministic SHACL generation
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 65536,
    "response_mime_type": "text/plain",
}

model_name = "gemini-2.5-pro-preview-03-25"
model = genai.GenerativeModel(
    model_name=model_name,
    generation_config=gemini_config,
)

print(f"Using Gemini model: {model_name}")
print(f"Input TTL directory: {doc_graph_dir}")
print(f"SHACL output directory: {shacl_output_dir}")

# --- Namespaces ---

FIREBIM = Namespace("http://example.com/firebim#") # Adjust if your namespace is different
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
FBBO = Namespace("http://example.com/fbbo#") 

# --- Helper Functions ---

def extract_article_member_text_from_ttl(ttl_content: str) -> list[tuple[str, str]]:
    """
    Parses TTL content to extract the original text (fro:hasOriginalText)
    associated with fro:Article subjects, recursively gathering text from
    all nested fro:Member subjects linked via fro:hasMember.

    Args:
        ttl_content: The Turtle content as a string.

    Returns:
        A list of tuples: (article_subject_uri, combined_full_text).
        The combined_full_text includes the article's text (if any) and the text
        of all its direct and nested members, separated by newlines. Only returns
        entries where there is *some* text found in the hierarchy.
    """
    g = Graph()
    try:
        g.parse(data=ttl_content, format="turtle")
        # Bind necessary prefixes for the query
        g.bind("firebim", FIREBIM)
        g.bind("rdf", RDF)
    except Exception as e:
        print(f"Warning: Could not parse TTL content: {e}")
        return []

    articles = []
    # Query 1: Find all Article subjects
    article_query = """
    SELECT ?article
    WHERE {
        ?article rdf:type fro:Article .
    }
    """
    try:
        results_article = g.query(article_query)
        articles = [str(row.article) for row in results_article]
    except Exception as e:
        print(f"Warning: Error querying Articles in TTL graph: {e}")
        return []

    if not articles:
        print("Warning: No fro:Article subjects found in the graph.")
        return []

    combined_texts_data = []

    # Query 2: For each article, find all text within its hierarchy
    # Uses SPARQL property path `fro:hasMember*` to find the article itself (0 steps)
    # and all nodes reachable via one or more `fro:hasMember` links.
    # Then retrieves `fro:hasOriginalText` from any of these nodes.
    text_hierarchy_query_template = """
    SELECT ?text
    WHERE {{
        <{article_uri}> fro:hasMember* ?node .
        ?node fro:hasOriginalText ?text .
    }}
    """
    # Note: We query text separately for each article to keep texts grouped.

    for article_uri in articles:
        all_texts_for_article = []
        try:
            # Execute the query for the current article
            query = text_hierarchy_query_template.format(article_uri=article_uri)
            results_text = g.query(query) # No need for initNs as prefixes are bound to graph

            for row in results_text:
                text_content = str(row.text).strip()
                # Basic cleaning (remove HTML-like tags) - adjust if needed
                text_content_cleaned = re.sub('<[^<]+?>', '', text_content)
                if text_content_cleaned: # Only add non-empty cleaned text
                    all_texts_for_article.append(text_content_cleaned)

        except Exception as e:
            print(f"Warning: Error querying text hierarchy for article {article_uri}: {e}")
            # Decide if you want to continue with other articles or stop
            continue # Continue to the next article

        # Combine the collected texts for this article
        if all_texts_for_article:
            combined_text = "\n".join(all_texts_for_article)
            combined_texts_data.append((article_uri, combined_text))
        # else:
            # Optional: Log if an article and its members had no text found
            # print(f"Debug: No text found for article {article_uri} or its members.")

    return combined_texts_data

# --- Global variable to cache SHACL docs content ---
shacl_documentation_content = None

def load_shacl_documentation(filepath: str) -> str:
    """Loads SHACL documentation from a file."""
    global shacl_documentation_content
    if shacl_documentation_content is None: # Load only once
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                shacl_documentation_content = f.read()
            print(f"Successfully loaded SHACL documentation from {filepath} ({len(shacl_documentation_content)} characters).")
            # Optional: Add a warning or truncation if the content is excessively large
            MAX_DOC_LEN = 5000000 # Example limit (adjust as needed)
            if len(shacl_documentation_content) > MAX_DOC_LEN:
                print(f"Warning: SHACL documentation content is very large ({len(shacl_documentation_content)} chars). Truncating to {MAX_DOC_LEN} chars for the prompt.")
                shacl_documentation_content = shacl_documentation_content[:MAX_DOC_LEN] + "\n... [TRUNCATED]"
        except FileNotFoundError:
            print(f"Warning: SHACL documentation file not found at {filepath}. Proceeding without it.")
            shacl_documentation_content = "[SHACL Documentation Not Found]"
        except Exception as e:
            print(f"Warning: Error reading SHACL documentation file {filepath}: {e}. Proceeding without it.")
            shacl_documentation_content = "[Error Reading SHACL Documentation]"
    return shacl_documentation_content

def generate_shacl_from_text(rule_text: str, rule_subject_uri: str, building_ontology_graph: Graph) -> str | None:
    """
    Uses Gemini to generate a SHACL shape in Turtle format directly from
    the original regulatory text associated with a specific subject URI,
    dynamically including SHACL documentation in the prompt.
    Attempts to clean markdown code fences from the response.

    Args:
        rule_text: The original text of the rule/article/member.
        rule_subject_uri: The URI of the rule/article/member in the source document graph.
        building_ontology_graph: An rdflib Graph object containing the building ontology.

    Returns:
        A string containing the generated SHACL shape in Turtle format, or None if generation fails.
    """
    # Load SHACL documentation content (cached after first load)
    shacl_docs = load_shacl_documentation(shacl_docs_path)

    # Basic ontology context
    ontology_prefixes = "\n".join([f"@prefix {prefix}: <{namespace}> ." for prefix, namespace in building_ontology_graph.namespaces()])

    # Dynamically create the system prompt including the loaded SHACL docs
    system_prompt = f"""You are an AI expert specializing in building regulations, Semantic Web technologies, SHACL, and building ontologies (like FIREBIM, BOT, etc.). Your task is to translate a given piece of regulatory text directly into a SHACL shape expressed in Turtle format. Use the provided SHACL documentation as a reference.

**Input:**
1.  **Regulatory Text:** The original text content of a specific rule, article, or section from a building code document.
2.  **Subject URI:** The unique identifier (`<{rule_subject_uri}>`) for this rule within its source document graph.
3.  **Ontology Context:** Assume the existence of relevant building ontology terms (prefixes provided below). Use appropriate terms from common building ontologies or the FIREBIM namespace (`fro:`) where applicable.
4.  **SHACL Documentation:** Reference information from the SHACL specification is included below.

**Ontology Prefixes Available:**
```turtle
@prefix sh: <{SH}> .
@prefix xsd: <{XSD}> .
@prefix fro: <{FIREBIM}> .
@prefix fbbo: <{FBBO}> . # Example Building Ontology namespace
# Add other relevant prefixes as needed
{ontology_prefixes}
```

**Task:**
Analyze the provided **Regulatory Text**. Identify the core requirements, conditions of applicability, exceptions, and any selections. Translate these logical components into a complete and valid SHACL NodeShape in Turtle format, consulting the **SHACL Documentation** provided below as needed.

**Mapping Guidance (RASE concepts as interpretation aid):**
*   **Applicability (`<a>`-like concepts):** Determine the `sh:targetClass`, `sh:targetSubjectsOf`, `sh:targetObjectsOf`, or conditions within property shapes.
*   **Requirement (`<r>`-like concepts):** Define constraints using `sh:property` (path, cardinality, type, value, range, pattern, etc.). Handle alternatives ("or").
*   **Exception (`<e>`-like concepts):** Model exceptions using `sh:not`, `sh:closed`, filters, or conditional logic.
*   **Selection (``-like concepts):** Influence the `sh:target` or use `sh:in`, `sh:or`.

**Output Requirements:**
*   Generate **only** the SHACL shape in valid Turtle format.
*   Start directly with `@prefix` or the NodeShape definition. Do **not** include explanations, apologies, or any text outside the Turtle syntax.
*   Create a `sh:NodeShape` (e.g., `:Shape_rule_subject_uri_local_name`).
*   Define `sh:target` appropriately.
*   Use relevant ontology properties (e.g., `fro:hasFireResistance`). Use placeholders if needed.
*   Include clear `sh:message` properties.
*   Ensure syntactically correct Turtle.

---
**SHACL Documentation Reference:**
```html
{shacl_docs}
```
---

Now, generate the SHACL shape for the following text, considering its subject URI is `<{rule_subject_uri}>`:
"""
    prompt = f"{system_prompt}\n\nRegulatory Text:\n```\n{rule_text}\n```\n\nGenerated SHACL Shape (Turtle):\n"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Note: Check if the final prompt size is within Gemini's limits
            # print(f"Prompt length: {len(prompt)} characters") # Optional: Check prompt size
            if len(prompt) > 30000: # Example check, adjust limit as needed based on model specifics
                 print(f"Warning: Prompt length ({len(prompt)} chars) is very large, potentially exceeding limits.")

            response = model.generate_content(
                prompt,
                generation_config=gemini_config,
            )

            raw_ttl = response.text.strip()
            generated_ttl = raw_ttl # Assume no code block initially

            # --- New: Check for and extract from ```turtle ... ``` code block ---
            match = re.search(r"```(?:turtle)?\s*(.*?)\s*```", raw_ttl, re.DOTALL | re.IGNORECASE)
            if match:
                extracted_content = match.group(1).strip()
                if extracted_content: # Ensure extracted content is not empty
                    print("Detected and extracted content from markdown code block.")
                    generated_ttl = extracted_content
                else:
                    print("Warning: Found markdown code block but content inside was empty.")
            # --- End New ---


            # Basic Validation on potentially extracted TTL
            if (generated_ttl.startswith("@prefix") or generated_ttl.startswith(":") or generated_ttl.startswith("<")) \
               and "sh:NodeShape" in generated_ttl:
                print(f"SHACL generation successful for subject: {rule_subject_uri}")
                try:
                    temp_graph = Graph()
                    temp_graph.parse(data=generated_ttl, format="turtle")
                    print("Generated SHACL parsed successfully (basic check).")
                    return generated_ttl
                except Exception as parse_error:
                    print(f"Warning: Generated SHACL failed basic parsing on attempt {attempt + 1}. Error: {parse_error}")
                    print(f"Generated TTL snippet:\n{generated_ttl[:500]}...") # Print snippet
            else:
                # If validation fails, print the original raw response for debugging if it differs
                original_response_info = f"(Original response was different: {raw_ttl[:100]}...)" if raw_ttl != generated_ttl else ""
                print(f"Warning: SHACL output does not look like valid Turtle on attempt {attempt + 1}. {original_response_info} Processed snippet:\n{generated_ttl[:500]}...")

        except Exception as e:
            # Handle potential API errors related to prompt size etc.
            print(f"Error: Gemini API call failed on attempt {attempt + 1}: {e}")
            if "size" in str(e).lower() or "limit" in str(e).lower():
                print("Error likely related to prompt size. Consider reducing SHACL documentation content.")

        if attempt < max_retries - 1:
            print(f"Retrying SHACL generation for {rule_subject_uri}...")
            time.sleep(5)

    print(f"Error: Failed to get valid SHACL Turtle after {max_retries} attempts for subject: {rule_subject_uri}")
    return None

# --- Main Processing Logic ---

def main():
    print("Starting direct Text-to-SHACL generation process...")

    # Ensure the SHACL docs path is defined globally or passed appropriately
    global shacl_docs_path
    if not os.path.exists(shacl_docs_path):
         print(f"CRITICAL WARNING: SHACL documentation file not found at '{shacl_docs_path}'. The prompt will indicate this.")
         # Optionally exit if the docs are essential:
         # return

    ttl_files = glob.glob(os.path.join(doc_graph_dir, "section_*.ttl"))
    if not ttl_files:
        print(f"Error: No TTL files found in {doc_graph_dir}. Ensure TTL generation ran successfully.")
        return

    # Load the building ontology
    building_ontology_path = "buildingontologies/firebim_ontology_notion.ttl"
    building_ontology_graph = Graph()
    try:
        print(f"Loading building ontology from {building_ontology_path}...")
        building_ontology_graph.parse(building_ontology_path, format="turtle")
        print(f"Loaded building ontology with {len(building_ontology_graph)} triples.")
    except Exception as e:
        print(f"Warning: Could not load building ontology from {building_ontology_path}: {e}")
        print("SHACL generation context will be limited.")

    combined_shacl_graph = Graph()
    # Bind namespaces
    combined_shacl_graph.bind("sh", SH)
    combined_shacl_graph.bind("xsd", XSD)
    combined_shacl_graph.bind("firebim", FIREBIM)
    combined_shacl_graph.bind("fbbo", FBBO)
    combined_shacl_graph.bind("dcterms", DCTERMS) # Add dcterms binding
    for prefix, namespace in building_ontology_graph.namespaces():
        combined_shacl_graph.bind(prefix, namespace)

    print(f"\n--- Found {len(ttl_files)} TTL files to process for SHACL generation ---")
    total_shacl_generated = 0

    for ttl_file_path in sorted(ttl_files):
        filename = os.path.basename(ttl_file_path)
        if "section_2" not in filename: # Remove or adjust any specific file filtering if needed
            continue
        print(f"\nProcessing {filename}...")

        try:
            with open(ttl_file_path, 'r', encoding='utf-8') as f:
                ttl_content = f.read()
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue

        # Use the updated extraction function
        article_texts_data = extract_article_member_text_from_ttl(ttl_content)
        if not article_texts_data:
            print(f"No Article text (with potential Member text) found in {filename}.")
            continue

        print(f"Found {len(article_texts_data)} Articles (with combined text) in {filename}.")

        file_shacl_count = 0
        # Iterate through the (article_uri, combined_text) tuples
        for article_uri, combined_rule_text in article_texts_data:
            print(f"  Generating SHACL for article: {article_uri}")
            if not combined_rule_text.strip():
                 print("    Skipping empty combined rule text.")
                 continue

            # Call the generation function with the article URI and combined text
            shacl_ttl_output = generate_shacl_from_text(combined_rule_text, article_uri, building_ontology_graph)

            if shacl_ttl_output:
                file_shacl_count += 1
                total_shacl_generated += 1

                # Option 1: Save individual SHACL files (using article URI)
                shacl_filename_base = article_uri.split('#')[-1] if '#' in article_uri else article_uri.split('/')[-1]
                shacl_filename_base = re.sub(r'[\\/*?:"<>|]', "_", shacl_filename_base)
                # Add prefix to distinguish article shapes easily
                shacl_output_filename = os.path.join(shacl_output_dir, f"shape_Article_{shacl_filename_base}.ttl")
                try:
                    with open(shacl_output_filename, 'w', encoding='utf-8') as f_shacl:
                        f_shacl.write(shacl_ttl_output)
                    # print(f"Saved SHACL shape to {shacl_output_filename}")
                except Exception as e:
                    print(f"Error writing individual SHACL file {shacl_output_filename}: {e}")

                # Option 2: Add generated TTL to a combined graph
                try:
                    combined_shacl_graph.parse(data=shacl_ttl_output, format="turtle")
                except Exception as e:
                    # Pass the article_uri for better error context
                    print(f"Error parsing generated SHACL for {article_uri} into combined graph: {e}\nContent snippet:\n{shacl_ttl_output[:500]}...")

        print(f"Generated {file_shacl_count} SHACL shapes (from Articles) from {filename}.")

    print(f"\n--- Direct Text-to-SHACL Generation Phase Complete ---")
    print(f"Total SHACL shapes generated (from Articles): {total_shacl_generated}")

    # Save the combined SHACL graph
    if total_shacl_generated > 0:
        combined_shacl_file = os.path.join(shacl_output_dir, f"{os.path.basename(input_file_base)}_combined_articles.shacl.ttl") # Modified filename
        try:
            combined_shacl_graph.serialize(destination=combined_shacl_file, format="turtle")
            print(f"Saved combined SHACL graph to {combined_shacl_file}")
        except Exception as e:
            print(f"Error saving combined SHACL graph: {e}")
    else:
        print("No SHACL shapes were generated to save in a combined file.")

    print("Processing finished.")

if __name__ == "__main__":
    main() 