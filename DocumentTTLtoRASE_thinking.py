import os
import glob
import json
import re
import time
from dotenv import load_dotenv
import google.generativeai as genai
from rdflib import Graph, Literal, URIRef, Namespace
from rdflib.namespace import RDF, RDFS

# Load environment variables
load_dotenv()

# --- Configuration ---
google_key = os.getenv("GEMINI_API_KEY")
input_file_base = os.getenv("INPUT_FILE") # e.g., 'NIT_198_crop.pdf'
if not input_file_base:
    raise ValueError("INPUT_FILE environment variable not set.")

# Define base directories based on input file
doc_graph_dir = f"documentgraphs/{input_file_base}"
rase_output_dir = f"RASE/{input_file_base}"
shacl_output_dir = f"SHACL/{input_file_base}" # Or a single file like f"SHACL/{input_file_base}.shacl.ttl"

# Ensure output directories exist
os.makedirs(rase_output_dir, exist_ok=True)
os.makedirs(shacl_output_dir, exist_ok=True)

# --- Gemini Model Setup ---
if not google_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

genai.configure(api_key=google_key)

# Configure the Gemini model (using Flash as requested)
# Note: Adjust model_name if needed based on availability
gemini_config = {
    "temperature": 0.2, # Lower temperature for more deterministic RASE/SHACL tasks
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192, # Increased for potentially complex outputs
    "response_mime_type": "text/plain", # Expecting JSON as text first
}

# Use a Gemini Flash model
model_name = "gemini-2.5-pro-exp-03-25" 
model = genai.GenerativeModel(
    model_name=model_name,
    generation_config=gemini_config,
    # system_instruction can be set here or per-request
)

print(f"Using Gemini model: {model_name}")
print(f"Input TTL directory: {doc_graph_dir}")
print(f"RASE output directory: {rase_output_dir}")
print(f"SHACL output directory: {shacl_output_dir}")


# --- Namespaces ---
FIREBIM = Namespace("http://example.com/firebim#")
# Add other namespaces if needed (FBBO, SHACL, etc.)
SH = Namespace("http://www.w3.org/ns/shacl#")

# --- Helper Functions ---

def extract_rule_text_from_ttl(ttl_content: str) -> list[tuple[str, str]]:
    """
    Parses TTL content to extract rule text, typically from firebim:hasOriginalText
    associated with Members or Articles. Returns a list of (subject_uri, text).
    """
    g = Graph()
    try:
        g.parse(data=ttl_content, format="turtle")
    except Exception as e:
        print(f"Warning: Could not parse TTL content: {e}")
        return []

    rule_texts = []
    # Query for original text associated with Articles or Members
    # Adjust the query based on where the actual rule text resides in your TTL structure
    query = """
    SELECT ?subject ?text
    WHERE {
        { ?subject rdf:type firebim:Article . }
        UNION
        { ?subject rdf:type firebim:Member . }
        ?subject firebim:hasOriginalText ?text .
        # Add FILTERs if needed, e.g., FILTER(lang(?text) = 'en')
    }
    """
    try:
        results = g.query(query, initNs={"firebim": FIREBIM, "rdf": RDF})
        for row in results:
            subject_uri = str(row.subject)
            text_content = str(row.text).strip()
            # Ignore very short or non-descriptive texts if necessary
            if text_content and len(text_content.split()) > 3: # Basic filter
                 # Remove HTML tags added in the previous step if they interfere
                text_content_cleaned = re.sub('<[^<]+?>', '', text_content)
                rule_texts.append((subject_uri, text_content_cleaned))
    except Exception as e:
        print(f"Warning: Error querying TTL graph: {e}")

    return rule_texts

def annotate_rule_with_rase(rule_text: str, context: str = "") -> str | None:
    """
    Uses Gemini to annotate a rule text by embedding RASE tags (<r>, <a>, <s>, <e>)
    within the text and wrapping the result in <R>, <A>, <S>, or <E> tags.

    Args:
        rule_text: The text of the rule to annotate.
        context: Optional surrounding context from the document section.

    Returns:
        A string containing the annotated rule text in the format:
        <X> Original text with <r>req</r >, <a>app</a >, <s>sel</s >, <e>exc</e > embedded </X>
        (where X is R, A, S, or E) or None if annotation fails.
    """
    system_prompt = """You are an AI assistant tasked with analyzing regulatory text and marking it up using a specific methodology called RASE. RASE stands for Requirement, Applicability, Selection, and Exception. Your goal is to identify these logical components within a given text and enclose the relevant phrases or clauses within specific XML-like tags.

**Your Task:**

Carefully read the regulatory text provided by the user. Apply RASE tags (`<R>`, `<A>`, `<S>`, `<E>` for main clauses/sentences, and `<r>`, `<a>`, `<s>`, `<e>` for specific phrases within them) to mark up the text according to the definitions and process below. Tag the *exact* text spans that correspond to each component. The entire output should be wrapped in the tag (`<R>`, `<A>`, `<S>`, or `<E>`) that best represents the overall nature of the provided text snippet.

**Understanding the RASE Components (Based on Semantic Mark-up Principles):**

 It is a characteristic of regulations that every ‘check’ must be in some way satisfied. The most obvious 
and most easily identified are the ‘requirements’ as these are associated with the future imperatives 
‘shall’ or ‘must’ ‘requirements’. It is required that a check contains at least one ‘requirement’. 
Secondly, there will be text that identifies the ‘applicability’ of the check. These are often 
304 of 982
compounded, for example ‘external windows’. These phrases need not relate directly to the topic of 
the regulation or the topic of the overall check. For example, if a check applies in ‘a seismic zone’, this 
is a property of the building site, not of the structural integrity of a particular building material. In 
general, there will be one or more phrases defining the applicability. One special but distinct case is 
where a ‘selection’ of alternative subjects or more ‘exceptions’. These are the opposite of 
‘applicability’, and conversely work by exclusion. (Nisbet, Wix and Conover, 2008). The RASE mark
up language uses the following four RASE operators: ‘requirement’ ‘applies, ‘select’, and ‘exception’.
 Applied on a text, the user highlights any clause or phrase that means:
 • ‘shall’/’must’ as a ‘requirement’, (including alternative requirements)
 • less scope as an ‘applies’
 • more scope as a ‘select’
 • ‘unless’  as an ‘exception’, (including composite exceptions).
The naming of the operator is chosen to correspond with the way standards, 
codes, regulative are written, which reflects natural language.
 The marked-up Requirement (R), Applicabilities (A), Selection (S) and Exceptions (E) clauses will 
contain phrases. The four types of phrases can be identically attributed to have a topic, a property, a 
comparator and a target value. The topic and property are ideally be drawn from a restricted dictionary 
composed of terms defined within the regulation and normal practice. The value (with any unit) may 
be numeric, whereupon the comparators will include ‘greater’, ‘lesser’, ‘equal’ and their converses. If 
the value is descriptive, then only the ‘equal’ or ‘not equal’ comparators are relevant. If the value 
represents a set of objects, then the comparator may be any of the set comparison operators such as 
‘includes’, ‘excludes’ (Hjelseth and Nisbet, 2010a and Nisbet, Wix and Conover, 2008).


1.  **R - Requirement:**
    *   **What it is:** This is the core obligation, the mandatory action, state, or performance criterion that *must* be fulfilled. It's the main point of the rule.
    *   **Keywords/Indicators:** Often uses "shall," "must," or specifies a non-negotiable condition, property, or metric (e.g., "width shall be 1.8m," "fire resistance must be EI 60").
    *   **Tag:** Use `<R>...</R>` for the main clause containing the requirement. Use `<r>...</r>` for the specific phrase detailing the metric, action, or state within that clause (e.g., `<r>not be steeper than 1:20</r>`). A single `<R>` clause can contain multiple `<r>` phrases if it lays out several specific requirements. Alternative ways to meet a requirement (e.g., using "or") should typically each be tagged as separate `<r>` phrases within the parent `<R>` clause.

2.  **A - Applicability:**
    *   **What it is:** This defines the scope or conditions under which the Requirement (R) applies. It tells you *when*, *where*, *to what*, or *under which circumstances* the rule is relevant.
    *   **Keywords/Indicators:** Often uses "if," "when," "for," "in cases where," "applies to," or phrases defining the subject, location, or situation (e.g., "for buildings open to the public," "in external walls," "where the distance is less than 3 metres").
    *   **Tag:** Use `<A>...</A>` for clauses defining applicability. Use `<a>...</a>` for specific phrases within a clause that define a condition or subject of applicability (e.g., `<a>external windows</a>`, `<a>distances of less than 3 metres</a>`). An `<R>` clause might be preceded by or contain multiple `<a>` phrases defining its scope.

3.  **S - Selection:**
    *   **What it is:** This component is used when the text explicitly offers a choice or selection regarding the *subjects* or *items* to which a rule (or part of a rule) applies. It often works *with* Applicability to refine the scope by *including* specific options from a potential set. It's about *selecting which things* are covered. *Distinguish this carefully from alternative Requirements (`<r>`) presented with "or".*
    *   **Keywords/Indicators:** Phrases that delineate specific choices among subjects, often paired with Applicability. (e.g., In the paper's example: "...for `<s>pedestrians</s>` `<s>wheelchair users</s>`...", these are selections within the applicability of the access route rule).
    *   **Tag:** Use `<S>...</S>` for clauses primarily focused on selection. Use `<s>...</s>` for the specific phrases naming the selected items/subjects.

4.  **E - Exception:**
    *   **What it is:** This defines conditions under which the Requirement (R) does *not* apply, or applies differently. It carves out specific cases from the general rule or modifies the requirement under certain circumstances.
    *   **Keywords/Indicators:** Often uses "unless," "except," "provided that," "however," "if not," "notwithstanding."
    *   **Tag:** Use `<E>...</E>` for clauses stating an exception. Use `<e>...</e>` for the specific phrase detailing the condition of the exception (e.g., `<e>unless the area is sprinklered</e>`, `<e>provided only if the judges chambers are not located close to the courtroom</e>`).

**Tagging Rules and Process:**

1.  **Read Thoroughly:** Understand the meaning and logical structure of the entire text snippet first.
2.  **Identify the Primary Nature:** Determine if the *overall snippet* primarily represents a Requirement, Applicability condition, Selection criteria, or an Exception.
3.  **Apply Outer Tag:** Wrap the entire snippet in the corresponding main tag (`<R>`, `<A>`, `<S>`, or `<E>`).
4.  **Identify Inner Components:** Within the main tagged block, identify the specific clauses or phrases corresponding to Requirements, Applicability, Selection, and Exception.
5.  **Apply Inner Clause Tags (Optional but helpful):** Enclose significant clauses with `<R>`, `<A>`, `<S>`, `<E>` if they represent a distinct logical component *within* the main block. Nesting is allowed (e.g., an `<E>` might be inside an `<R>`).
6.  **Apply Phrase-Level Tags (`<r>`, `<a>`, `<s>`, `<e>`):** Within the tagged clauses (or directly within the main block if no inner clause tags are used), refine the markup by enclosing the *specific* words or phrases that define the metric, condition, subject, or exception. These are often the most crucial parts for automated checking.
7.  **Tag Exact Text:** Ensure your tags enclose *only* the relevant text span. Do not add or change words.
8.  **Prioritize Clarity:** If a phrase seems ambiguous, apply the tag that best reflects its primary logical function in the context of the rule.
9.  **Output:** Provide *only* the fully tagged text as your response, wrapped in the single primary tag determined in step 2.

**Example 1:**

**Original Text:**
`5.2 Dimensioning an access route to a building
 The access route for pedestrians/wheelchair users shall not be steeper than 1:20. For 
distances of less than 3 metres, it may be steeper, but not more than 1:12. 
The access route shall have clear width of a minimum of 1,8 m and obstacles shall be placed 
so that they do not reduce that width. Maximum cross fall shall be 2 %.
 The access route shall have a horizontal landing at the start and end of the incline, plus a 
horizontal landing for every 0,6 m of incline. The landing shall be a minimum of 1,6 m deep.
 Minimum clear height shall be 2,25 m for the full width of the defined walking zone of the 
entire access route including crossing points.`

**RASE Tagged Output:**
`<R>5.2 Dimensioning an <a>access route</a> to a building
 <R> The <a>access route</a> for <s>pedestrians</s><s>wheelchair users</s> shall <r>not 
be steeper than 1:20</r>. <E>For <a>distances of less than 3 metres</a>, it may be steeper, 
but <r>not more than 1:12</r>.</E></R>
 <R>The <a>access route</a> shall have <r>clear width of a minimum of 1,8 m</r> and
 <r>obstacles shall be placed so that they do not reduce that width </r>.<r>Maximum cross fall 
shall be 2 %.</r></R>
 <R>The <a>access route</a> shall have <r>a horizontal landing at the start and end of the in
cline<r>, plus <r>a horizontal landing for every 0,6 m of incline</r>. <r>The landing shall be a 
minimum of 1,6 m deep.</r></R>
 <R><r>Minimum clear height shall be 2,25 m </r>for the full width of the defined walking zone 
of the entire <a>access route</a> including crossing points. </R></R>`

Example 2:

**Original Text:**
`Major Spaces: The activities of the USDC focus on the courtroom. The courtroom requires direct access from 
public, restricted, and secure circulation. Ancillary spaces located near the district courtroom 
include: attorney/witness conference rooms accessed from public circulation; judge's conference 
robing room (provided only if the judges chambers are not located close to the courtroom) 
accessed from restricted circulation; trial jury suite accessed directly from the courtroom or 
restricted circulation; and prisoner holding cells accessed from secure circulation.`

**RASE Tagged Output:**
`<R>Major <a>Spaces</a>
 The activities of the USDC focus on the courtroom. <R>The <R>courtroom</a> requires 
<r>direct access from public</r>, <r>restricted</r>, and <r>secure circulation<r>
 </r></R></R><a>Ancillary spaces</a> located <r>near the district courtroom<r> 
include: <R><R><a>attorney/witness conference rooms</a> accessed from <r>public 
circulation</r></R>; <R><a>judge's conference robing room</a> <E>(provided only if 
the <a>judges chambers<a> are <r>not located close to the courtroom</r>)</E>
 accessed from <r>restricted circulation</r></R>; <R><a>trial jury suite</a> accessed 
directly from the <R><s>courtroom</s> or <s>restricted circulation</s></R></R>; and 
<R><a>prisoner holding cells</a> accessed from <r>secure circulation</r></R> .</R>.`

Make sure your output is only the RASE annotated text, no other text or formatting or code blocks or anything else.

**Now, await the user's input text.**
"""
    prompt = f"Instruction: {system_prompt}\nRule Text:\n```\n{rule_text}\n```\n"
    if context:
        prompt += f"\nContext:\n```\n{context}\n```\n"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=gemini_config,
                # Consider adding system_instruction=system_prompt here if preferred
            )

            # Clean up potential markdown code fences or other surrounding text
            annotated_text = response.text.strip()

            # Updated validation: check if it starts/ends with any of the main RASE tags
            starts_valid = any(annotated_text.startswith(f"<{tag}>") for tag in "RASE")
            ends_valid = any(annotated_text.endswith(f"</{tag}>") for tag in "RASE")
            # Optional: Ensure start and end tags match (more robust)
            match = re.match(r"^<([RASE])>.*</\1>$", annotated_text, re.DOTALL)

            if match: # Check if start and end tags match and are one of R, A, S, E
                 # Further check: does it contain at least one of the inner tags? (Optional but good)
                 if re.search(r'<[rase]>', annotated_text):
                     print(f"RASE annotation successful for rule snippet.")
                     return annotated_text
                 else:
                     # If no inner tags are found, it might be a simple A/E/S block. Accept it.
                     print(f"RASE annotation completed, but no inner <r/a/s/e> tags found. Accepting.")
                     return annotated_text
            elif starts_valid and ends_valid:
                 # Fallback if regex fails but basic start/end looks okay (less strict)
                 print(f"RASE annotation completed (basic validation passed).")
                 return annotated_text
            else:
                print(f"Warning: RASE output does not start/end with matching <R/A/S/E> tags on attempt {attempt + 1}. Response: {annotated_text}")


        except Exception as e:
            print(f"Error: Gemini API call failed on attempt {attempt + 1}: {e}")

        if attempt < max_retries - 1:
            time.sleep(5) # Wait before retrying

    print(f"Error: Failed to get valid RASE annotation after {max_retries} attempts for rule: {rule_text[:100]}...")
    return None

def generate_shacl_from_rase(rase_annotated_rule: str, rule_subject_uri: str, building_ontology_graph: Graph) -> str | None:
    """
    Placeholder function to generate SHACL shapes from RASE annotated rule text
    (which is expected to be wrapped in <R>, <A>, <S>, or <E> tags).
    Requires parsing the embedded tags.
    """
    print(f"--- Generating SHACL for {rule_subject_uri} (Placeholder) ---")
    # Extract the outer tag to understand the primary nature (R, A, S, E)
    outer_tag_match = re.match(r"^<([RASE])>", rase_annotated_rule)
    outer_tag = outer_tag_match.group(1) if outer_tag_match else "Unknown"
    print(f"RASE Input Rule Text (Outer tag: {outer_tag}): {rase_annotated_rule}")

    # --- Complex Logic Needed Here ---
    # 1. Parse the rase_annotated_rule string to extract text associated with <r>, <a>, <s>, <e> tags.
    #    The overall structure might depend on the outer tag (R, A, S, E).
    # 2. Identify Target based on text within <a> tags, potentially influenced by the outer tag.
    # 3. Map Requirement text (<r> tags) to SHACL constraints.
    # 4. Handle Selection (<s> tags) and Exception (<e> tags).
    # 5. Construct SHACL graph. Consider how the outer tag influences the shape's nature.
    #    - If outer is <A>, maybe it primarily defines a target?
    #    - If outer is <E>, maybe it defines a `sh:not` or filter condition?

    # Example LLM Prompt (Further refinement needed):
    # system_prompt = f"""You are an expert in SHACL and building ontologies.
    # Given a building code rule annotated with inline RASE tags (<r>, <a>, <s>, <e>) and wrapped in a primary RASE tag (<R>, <A>, <S>, or <E>),
    # and relevant building ontology snippets, generate a SHACL shape in Turtle format.
    # The outer tag indicates the overall nature of the rule snippet.
    # Map RASE components to SHACL:
    # - Text within <a> tags often defines the sh:targetClass or conditions for applying constraints.
    # - Text within <r> tags defines the core constraints (sh:property, sh:minCount, sh:datatype, sh:hasValue, etc.).
    # - Text within <e> tags often maps to sh:not or filters within properties.
    # - Text within <s> tags might use sh:or or influence target selection.
    # Adapt the SHACL structure based on the outer tag ({outer_tag}).
    # Use the provided ontology terms. The target rule subject was {rule_subject_uri}.
    # Building Ontology Snippet: [Provide relevant parts of building_ontology_graph here]
    # RASE Annotated Rule: {rase_annotated_rule}
    # Generate ONLY the SHACL Turtle code for a NodeShape reflecting this rule fragment.
    # """
    # prompt = "Generate the SHACL shape."
    # ... (rest of placeholder logic) ...

    # --- Placeholder Return ---
    shape_name = f"Shape_{rule_subject_uri.split('#')[-1]}" if '#' in rule_subject_uri else f"Shape_{rule_subject_uri.split('/')[-1]}"
    shacl_placeholder = f"""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix firebim: <{FIREBIM}> .
# Add other prefixes (FBBO, INST, etc.)

# SHACL Shape derived from inline RASE annotated text for {rule_subject_uri}
# Outer RASE tag detected: {outer_tag}
<{shape_name}>
    a sh:NodeShape ;
    # TODO: Determine target based on <a> tags and potentially outer tag {outer_tag}
    sh:targetClass firebim:PlaceholderTarget ;
    sh:message "Placeholder shape based on inline RASE annotation (Outer: {outer_tag}) for {rule_subject_uri}" ;
    # TODO: Add constraints based on <r> tags
    # TODO: Add filters/negations based on <e> tags (potentially using sh:not if outer_tag is E)
    # TODO: Add logic based on <s> tags
    sh:property [
        sh:path firebim:placeholderProperty ; # TODO: Determine property path
        sh:minCount 1 ; # Example constraint
    ] .
"""
    print("--- SHACL Generation requires significant implementation ---")
    return shacl_placeholder # Return placeholder TTL string

# --- Main Processing Logic ---

def main():
    print("Starting RASE annotation process...")

    ttl_files = glob.glob(os.path.join(doc_graph_dir, "section_*.ttl"))
    if not ttl_files:
        print(f"Error: No TTL files found in {doc_graph_dir}. Did DocumentPDFtoMDtoTTL.py run successfully?")
        return

    all_rase_rules = {} # Store RASE results {subject_uri: rase_rule_text}

    # --- Step 1: RASE Annotation ---
    print(f"\n--- Found {len(ttl_files)} TTL files to process for RASE annotation ---")
    for ttl_file_path in sorted(ttl_files):
        filename = os.path.basename(ttl_file_path)
        if "section_2_2_1" not in filename:
            continue
        print(f"Processing {filename}...")

        try:
            with open(ttl_file_path, 'r', encoding='utf-8') as f:
                ttl_content = f.read()
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue

        rule_texts = extract_rule_text_from_ttl(ttl_content)
        if not rule_texts:
            print(f"No suitable rule text found in {filename}.")
            continue

        print(f"Found {len(rule_texts)} rule snippets in {filename}.")
        section_annotated_rules = [] # Store list of (subject_uri, <R/A/S/E> block) for this file

        for subject_uri, rule_text in rule_texts:
            print(f"  Annotating rule for subject: {subject_uri}")
            # Add context=context if needed from surrounding TTL elements
            rase_result_rule = annotate_rule_with_rase(rule_text)

            if rase_result_rule:
                section_annotated_rules.append((subject_uri, rase_result_rule))
                all_rase_rules[subject_uri] = rase_result_rule # Add to global dict

        # Save RASE results for this section TTL file as a single .rase.xml file
        if section_annotated_rules:
            # Use .rase.xml extension to indicate content type
            rase_output_filename = os.path.join(rase_output_dir, f"{os.path.splitext(filename)[0]}.rase.xml")
            try:
                with open(rase_output_filename, 'w', encoding='utf-8') as f_out:
                    # Write the R/A/S/E blocks directly, potentially wrapped in a root element
                    f_out.write("<rules>\n") # Optional root element
                    for subj, rase_rule in section_annotated_rules:
                        #f_out.write(f"  <!-- Rule Source: {subj} -->\n")
                        f_out.write(f"  {rase_rule}\n")
                    f_out.write("</rules>\n") # Close optional root element
                print(f"Saved RASE annotated rules to {rase_output_filename}")
            except Exception as e:
                print(f"Error saving RASE rules for {filename}: {e}")

    print("\n--- RASE Annotation Phase Complete ---")

    # --- Step 2: SHACL Generation (Placeholder Implementation) ---
    print("\n--- Starting SHACL Generation (Placeholder) ---")
    if not all_rase_rules:
        print("No RASE annotations were generated. Skipping SHACL generation.")
        return

    # Load the building ontology (needed for context in real SHACL generation)
    building_ontology_path = "buildingontologies/firebim_ontology_notion.ttl" # Adjust path if needed
    building_ontology_graph = Graph()
    try:
        print(f"Loading building ontology from {building_ontology_path}...")
        building_ontology_graph.parse(building_ontology_path, format="turtle")
        print(f"Loaded building ontology with {len(building_ontology_graph)} triples.")
    except Exception as e:
        print(f"Warning: Could not load building ontology from {building_ontology_path}: {e}")
        print("SHACL generation context will be limited.")
        # Proceed without ontology graph, or handle error differently

    combined_shacl_graph = Graph()
    # Bind namespaces to the combined graph
    combined_shacl_graph.bind("sh", SH)
    combined_shacl_graph.bind("firebim", FIREBIM)
    # Add other necessary namespaces (FBBO, INST, XSD, etc.)

    shacl_count = 0
    # Now iterate through the collected RASE rules (<R/A/S/E> blocks)
    for subject_uri, rase_rule_text in all_rase_rules.items():
        # Pass the annotated rule text to the SHACL generation function
        shacl_ttl_output = generate_shacl_from_rase(rase_rule_text, subject_uri, building_ontology_graph)

        if shacl_ttl_output:
            shacl_count += 1
            # Option 1: Save individual SHACL files
            shacl_filename_base = subject_uri.split('#')[-1] if '#' in subject_uri else subject_uri.split('/')[-1]
            # Sanitize filename base if needed
            shacl_filename_base = re.sub(r'[\\/*?:"<>|]', "_", shacl_filename_base)
            shacl_output_filename = os.path.join(shacl_output_dir, f"shape_{shacl_filename_base}.ttl")
            try:
                with open(shacl_output_filename, 'w', encoding='utf-8') as f_shacl:
                    f_shacl.write(shacl_ttl_output)
                # print(f"Saved placeholder SHACL shape to {shacl_output_filename}")

                # Option 2: Add to a combined graph (also parse the generated TTL)
                try:
                    combined_shacl_graph.parse(data=shacl_ttl_output, format="turtle")
                except Exception as e:
                    print(f"Error parsing generated SHACL for {subject_uri}: {e}\nContent:\n{shacl_ttl_output}")

            except Exception as e:
                print(f"Error writing SHACL file {shacl_output_filename}: {e}")

    print(f"\nGenerated {shacl_count} placeholder SHACL shapes.")

    # Save the combined SHACL graph (if using Option 2)
    if shacl_count > 0:
        combined_shacl_file = os.path.join(shacl_output_dir, f"{os.path.basename(input_file_base)}_combined.shacl.ttl")
        try:
            combined_shacl_graph.serialize(destination=combined_shacl_file, format="turtle")
            print(f"Saved combined placeholder SHACL graph to {combined_shacl_file}")
        except Exception as e:
            print(f"Error saving combined SHACL graph: {e}")

    print("\n--- SHACL Generation Phase Complete ---")
    print("Processing finished.")

if __name__ == "__main__":
    main()
