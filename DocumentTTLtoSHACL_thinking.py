import os
import glob
import json
import re
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
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

# --- Document-specific Ontology Configuration ---
# Set the country code for the document being processed.
# Country-specific ontology terms (e.g. fbo-be:) will be preferred over generic fbo: terms.
# Supported values: "BE", "NL", "DK", "PT", "LT"
DOCUMENT_COUNTRY_CODE = "BE"

# The unified ontology already contains all FBO terms (base + all country variants).
unified_ontology_path = "fbo/firebim_ontology_unified.ttl"

# Ensure output directory exists
os.makedirs(shacl_output_dir, exist_ok=True)

# --- Gemini Model Setup ---

if not google_key:
    raise ValueError("GEMINI_API_KEY environment variable not set.")

gemini_client = genai.Client(api_key=google_key)

model_name = "gemini-3.1-pro-preview"

print(f"Using Gemini model: {model_name}")
print(f"Input TTL directory: {doc_graph_dir}")
print(f"SHACL output directory: {shacl_output_dir}")

# --- Namespaces ---

FRO = Namespace("http://www.firebim.org/ontologies/fro#")
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
FBO = Namespace("http://www.firebim.org/ontologies/fbo#") 

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
        g.bind("fro", FRO)
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

def extract_ontology_terms_catalog(graph: Graph, catalog_label: str = "ontology") -> str:
    """
    Extracts all owl:Class, owl:DatatypeProperty, and owl:ObjectProperty subjects
    from an ontology graph and returns a formatted catalog string.

    The catalog lists each term as a prefixed name (e.g. fbo-be:Atrium) with its
    English rdfs:label, so the LLM knows exactly which identifiers exist.

    Args:
        graph: An rdflib Graph containing the parsed ontology.
        catalog_label: A human-readable name for log messages only.

    Returns:
        A multi-line string enumerating every defined term, or a placeholder if empty.
    """
    OWL = Namespace("http://www.w3.org/2002/07/owl#")
    type_labels = {
        str(OWL.Class): "Class",
        str(OWL.DatatypeProperty): "DatatypeProperty",
        str(OWL.ObjectProperty): "ObjectProperty",
    }

    lines = []
    for type_uri, type_label in type_labels.items():
        for subj in sorted(graph.subjects(RDF.type, URIRef(type_uri)), key=str):
            try:
                prefixed = graph.namespace_manager.qname(subj)
            except Exception:
                prefixed = str(subj)

            # Prefer an English label; fall back to any label
            en_label = None
            any_label = None
            for lbl in graph.objects(subj, RDFS.label):
                lang = getattr(lbl, "language", None)
                if lang == "en" and en_label is None:
                    en_label = str(lbl)
                elif any_label is None:
                    any_label = str(lbl)
            display_label = en_label or any_label

            entry = f"  - {prefixed} ({type_label})"
            if display_label:
                entry += f': "{display_label}"'
            lines.append(entry)

    if not lines:
        return f"  [No terms found in {catalog_label}]"
    return "\n".join(lines)


def generate_shacl_from_text(
    rule_text: str,
    rule_subject_uri: str,
    ontology_graph: Graph,
) -> str | None:
    """
    Uses Gemini to generate a SHACL shape in Turtle format directly from
    the original regulatory text associated with a specific subject URI.
    Includes the full catalog of defined ontology terms in the prompt so the
    model strongly prefers terms that actually exist in the ontology.

    Args:
        rule_text: The original text of the rule/article/member.
        rule_subject_uri: The URI of the rule/article/member in the source document graph.
        ontology_graph: rdflib Graph of the unified FBO ontology (contains base + all country terms).

    Returns:
        A string containing the generated SHACL shape in Turtle format, or None if generation fails.
    """
    # Load SHACL documentation content (cached after first load)
    shacl_docs = load_shacl_documentation(shacl_docs_path)

    # Collect namespace prefixes from the ontology graph
    ontology_prefixes = "\n".join(
        f"@prefix {p}: <{ns}> ."
        for p, ns in sorted((str(p), str(ns)) for p, ns in ontology_graph.namespaces())
    )

    # Determine the country namespace URI so we can split the catalog into two sections
    country_prefix = f"fbo-{DOCUMENT_COUNTRY_CODE.lower()}"
    country_ns_uri = next(
        (str(ns) for p, ns in ontology_graph.namespaces() if str(p) == country_prefix),
        None,
    )

    # Build term catalogs: country-specific terms first, then base fbo: terms
    # Filter by namespace URI prefix so both come from the single unified graph
    def _catalog_for_ns(ns_uri: str | None) -> str:
        """Return catalog lines for terms whose URI starts with ns_uri."""
        if ns_uri is None:
            return "  [Namespace not found in ontology]"
        filtered = Graph()
        filtered.namespace_manager = ontology_graph.namespace_manager
        OWL = Namespace("http://www.w3.org/2002/07/owl#")
        for type_uri in (OWL.Class, OWL.DatatypeProperty, OWL.ObjectProperty):
            for subj in ontology_graph.subjects(RDF.type, type_uri):
                if str(subj).startswith(ns_uri):
                    for t in ontology_graph.triples((subj, None, None)):
                        filtered.add(t)
        return extract_ontology_terms_catalog(filtered, ns_uri)

    base_ns_uri = next(
        (str(ns) for p, ns in ontology_graph.namespaces() if str(p) == "fbo"),
        None,
    )
    country_terms_catalog = _catalog_for_ns(country_ns_uri)
    base_terms_catalog = _catalog_for_ns(base_ns_uri)

    # Dynamically create the system prompt including the loaded SHACL docs
    system_prompt = f"""You are an AI expert specializing in building regulations, Semantic Web technologies, SHACL, and building ontologies (like FRO, FBO, BOT, etc.). Your task is to translate a given piece of regulatory text directly into a SHACL shape expressed in Turtle format. Use the provided SHACL documentation as a reference.

**Input:**
1.  **Regulatory Text:** The original text content of a specific rule, article, or section from a building code document.
2.  **Subject URI:** The unique identifier (`<{rule_subject_uri}>`) for this rule within its source document graph.
3.  **Ontology Term Catalogs:** The exhaustive lists of every class and property defined in the building ontology are provided below. You MUST restrict yourself to these terms.
4.  **SHACL Documentation:** Reference information from the SHACL specification is included below.

**Ontology Prefixes:**
```turtle
@prefix sh: <{SH}> .
@prefix xsd: <{XSD}> .
@prefix fro: <{FRO}> .
{ontology_prefixes}
```

---
**Ontology Term Usage — Important Guidelines:**

The catalogs below list every class and property defined in the building ontology. You should **strongly prefer** these terms over any others.

**Priority rule:** Always prefer country-specific terms (`fbo-{DOCUMENT_COUNTRY_CODE.lower()}:`) over generic FBO terms (`fbo:`) when both describe the same concept.

Only use a term that is **not** in the catalogs below as an absolute last resort — i.e. when no existing term even partially covers the concept. If you do invent a term outside the ontology, add a `# NOTE: no ontology term found` comment on that line so it is easy to review.

**Available country-specific terms — USE THESE FIRST (`fbo-{DOCUMENT_COUNTRY_CODE.lower()}:`):**
{country_terms_catalog}

**Available base FBO terms — use when no country-specific equivalent exists (`fbo:`):**
{base_terms_catalog}
---

**Task:**
Analyze the provided **Regulatory Text** with the goal of producing a **maximally complete and faithful** SHACL representation. Your output must be a 1-to-1 translation of the regulatory text into SHACL — nothing omitted, nothing simplified, nothing merged. The SHACL output should be so thorough that someone reading ONLY the shapes could reconstruct the full meaning of the original regulation.

**CRITICAL — Completeness Rules (violations are unacceptable):**

A. **Every distinct rule, sub-rule, bullet point, list item, and table row** in the text MUST produce its own `sh:PropertyShape` or `sh:NodeShape`. Do NOT merge multiple rules into one shape. If the text has 5 bullet points, you need at least 5 property constraints. If the text has a table with 4 data rows, each row must be represented.

B. **Tables are especially important.** Each cell combination in a regulatory table represents a distinct requirement. For a table with N rows × M columns of requirements, you need N×M constraints (or N shapes with M properties each). Every row header, column header, and cell value must appear in the SHACL. Model tables as separate `sh:NodeShape`s per row or per logical grouping, with `sh:property` constraints matching each column value.

C. **Footnotes, notes, and parenthetical exceptions** (e.g., "(*) except when...", "sauf si...", "pour autant que...") are MANDATORY to model. These often contain the most critical constraints — percentage thresholds, material exclusions, sealing requirements. Each footnote must become an explicit `sh:not`, `sh:or` alternative, or separate conditional shape. Never ignore footnotes.

D. **Conditional logic must be precise:**
   - "condition A AND condition B" → `sh:and ( [...] [...] )`
   - "condition A OR condition B" → `sh:or ( [...] [...] )`
   - "X unless/except Y" → main shape for X, plus `sh:not` or `sh:or` alternative for Y
   - "both of the following conditions" → `sh:and`, NEVER `sh:or`
   - When the text says requirements from two tables must be met "simultaneously", model them as `sh:and`.

E. **Every numeric value** must be captured with its exact quantity, unit, and comparison operator:
   - "≥ 1 m" → `sh:minInclusive 1.0` with datatype
   - "≤ 20 mm" → `sh:maxInclusive 20` with datatype
   - "≥ 0,6 m" → `sh:minInclusive 0.6` with datatype
   - "60 minutes" → explicit duration constraint
   - Percentages like "< 5%" → `sh:maxExclusive 5.0`
   Do NOT approximate or round. Use the exact values from the text.

F. **Definitions and criteria** stated in the text (e.g., what fire stability R means, what integrity E means, what insulation I means) must each become their own shape or property constraint with the full definition captured in `sh:description` or `sh:message`. Do not skip definitional content — it establishes the semantic meaning of terms used elsewhere.

G. **Classification systems and indices** (e.g., fire direction i→o, o→i, i↔o; the 'ef' suffix for external fire curve; Euro-class fire reaction ratings A1, A2, B, C, D, E, F) must be modeled as structured constraints, not just free-text strings. Use `sh:in` lists, `sh:pattern` regex, or `sh:hasValue` as appropriate.

H. **Cross-references** (e.g., "see Table 6", "see article 3.5.1.1") should be noted in `sh:description` or comments. If the referenced content IS present in the text (e.g., the table is included), model it fully. If the reference is to external content not in the provided text, add a `# See: [reference]` comment.

I. **Material exclusions and prohibitions** (e.g., "EPS and XPS are not permitted") must be explicitly modeled with `sh:not` constraints, not just omitted from an `sh:in` list.

J. **Alternative solutions** (e.g., "alternatively, a horizontal projection of ≥ 0.6 m") must be modeled as a separate `sh:or` branch with all their own specific constraints.

Work through the text systematically:
1. **Scope / applicability conditions** — what type of building, space, element, or situation does the rule apply to? These conditions must become part of `sh:target` or an enclosing filter/pre-condition, NOT be silently dropped. For example, if the rule says "ground-floor compartments", the shape must explicitly target only ground-floor compartments, not all compartments.
2. **Core requirements** — the actual constraint(s) that must hold.
3. **Exceptions and special cases** — model each one explicitly (e.g. with `sh:or`, `sh:not`, a separate `sh:NodeShape`, or a SPARQL-based constraint).
4. **Quantitative thresholds** — capture every numeric value, unit, and comparison operator exactly as stated.

If the text contains multiple independent sub-rules, generate a separate `sh:NodeShape` for each one. When in doubt, generate MORE shapes rather than fewer.

**Output Requirements:**
*   Generate **only** the SHACL shape(s) in valid Turtle format.
*   Start directly with `@prefix` declarations or the NodeShape definition. Do **not** include explanations, apologies, or any text outside the Turtle syntax.
*   Create one or more `sh:NodeShape`s (e.g., `:Shape_rule_subject_uri_local_name`).
*   `sh:target` (or equivalent targeting) must encode ALL applicability conditions from the text — never broaden the target beyond what the rule actually covers but also never simplify the rule. The text must be translated as directly as possible, even if it means the rule is way more complicated.
*   Strongly prefer ontology terms from the catalogs above. Only use a term outside the catalogs as a last resort; if you do, add a `# NOTE: no ontology term found` comment on that line.
*   Include clear `sh:message` properties on **every** constraint, quoting the relevant fragment of the original text verbatim.
*   Include `sh:description` on each `sh:NodeShape` summarizing what aspect of the regulation it encodes.
*   Ensure syntactically correct Turtle.

**Self-check before outputting:** Count the number of distinct requirements, conditions, exceptions, table rows, and bullet points in the input text. Your SHACL output must have at least that many constraints. If your output has fewer constraints than the input has distinct regulatory statements, you have oversimplified — go back and add the missing ones.


Now, generate the SHACL shape for the following text, considering its subject URI is `<{rule_subject_uri}>`:
"""
    prompt = (
        f"{system_prompt}\n\nRegulatory Text:\n```\n{rule_text}\n```\n\n"
        f"Generated SHACL Shape (Turtle):\n"
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Note: Check if the final prompt size is within Gemini's limits
            # print(f"Prompt length: {len(prompt)} characters") # Optional: Check prompt size
            if len(prompt) > 30000: # Example check, adjust limit as needed based on model specifics
                 print(f"Warning: Prompt length ({len(prompt)} chars) is very large, potentially exceeding limits.")

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                    ],
                ),
            ]
            generate_content_config = types.GenerateContentConfig(
                temperature=1,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=8192,
                ),
            )
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=generate_content_config,
            )

            raw_ttl = response.text.strip() if response.text else ""
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

    # Load the unified FBO ontology (contains base + all country-specific terms)
    ontology_graph = Graph()
    try:
        print(f"Loading unified FBO ontology from {unified_ontology_path}...")
        ontology_graph.parse(unified_ontology_path, format="turtle")
        print(f"Loaded unified FBO ontology with {len(ontology_graph)} triples.")
    except Exception as e:
        print(f"Warning: Could not load unified FBO ontology from {unified_ontology_path}: {e}")
        print("SHACL generation context will be limited.")

    combined_shacl_graph = Graph()
    combined_shacl_graph.bind("sh", SH)
    combined_shacl_graph.bind("xsd", XSD)
    combined_shacl_graph.bind("fro", FRO)
    combined_shacl_graph.bind("dcterms", DCTERMS)
    for prefix, namespace in ontology_graph.namespaces():
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
            shacl_ttl_output = generate_shacl_from_text(combined_rule_text, article_uri, ontology_graph)

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