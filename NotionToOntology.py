import os
import requests
import json
from dotenv import load_dotenv
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL
import re

# --- Configuration ---
load_dotenv()
NOTION_KEY = os.environ.get("NOTION_KEY")

# Database IDs 
DB_UNIFIED = "d1163f8f04824d54bbfc4541fb327f06" 
DB_COUNTRIES = "153f8487e6e780aebc37db28dbb23feb" 

# NOTION PROPERTY NAMES MAPPING
# Update these strings if they look different in your specific Notion Database
PROP_MAP = {
    "Term": "TM - Harmonized Term",       # Title field
    "Name_EN": "TM - Name (English)",
    "Name_Native": "TM - Name (native language)",
    "Country": "Country",                 # Relation
    "Type": "TD - Type",                  # Select (Object/Property)
    "Unit": "TD - Unit",
    "ValueType": "TD - Value",
    "Def_Explicit_EN": "TC - Explicit Definition (English)",
    "Def_Implicit_EN": "TC - Implicit Definition  (English)",
    "Def_Explicit_Nat": "TC - Explicit Definition (Native Language) ", # Note the space
    "Def_Implicit_Nat": "TC - Implicit Definition  (Native Language)",
    "ISO_Def": "TR - ISO definition",
    "ArticleID": "TC - Article ID (it depends of the country)",
    "IFC_Entity": "TD - IFC Entity",
    "Parent": "item principal",           # Relation to parent item
    "Linked_Props": "Property is linked to EU terms or other Harmonized Terms" # Relation
}

headers = {
    'Authorization': f"Bearer {NOTION_KEY}", 
    'Content-Type': 'application/json', 
    'Notion-Version': '2022-06-28'
}

# --- Helpers ---

def clean_text(text):
    """Remove NA, N/A, and trim whitespace."""
    if not text: return None
    t = str(text).strip()
    if t.upper() in ["NA", "N/A", "NONE", "NULL"]:
        return None
    return t

def get_all_pages(database_id):
    all_pages = []
    has_more = True
    start_cursor = None
    
    print(f"Connecting to Notion Database: {database_id}...")
    
    while has_more:
        body = {}
        if start_cursor:
            body["start_cursor"] = start_cursor
            
        try:
            response = requests.post(
                f'https://api.notion.com/v1/databases/{database_id}/query', 
                headers=headers,
                json=body
            )
            response.raise_for_status()
            data = response.json()
            all_pages.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            if has_more:
                start_cursor = data.get("next_cursor")
        except Exception as e:
            print(f"Error fetching Notion: {e}")
            has_more = False
            
    print(f"  > Retrieved {len(all_pages)} items.")
    return all_pages

def get_property_value(page_properties, target_name):
    """Robust extraction with fuzzy matching for keys."""
    prop = page_properties.get(target_name)
    
    # Fuzzy match if exact key missing (handles trailing spaces)
    if not prop:
        for key in page_properties.keys():
            if key.strip() == target_name.strip():
                prop = page_properties[key]
                break
    
    if not prop: return None

    ptype = prop["type"]
    val = None
    
    if ptype == "title" and prop["title"]:
        val = "".join([t["plain_text"] for t in prop["title"]])
    elif ptype == "rich_text" and prop["rich_text"]:
        val = "".join([t["plain_text"] for t in prop["rich_text"]])
    elif ptype == "select" and prop["select"]:
        val = prop["select"]["name"]
    elif ptype == "multi_select":
        val = [item["name"] for item in prop["multi_select"]]
    elif ptype == "relation":
        val = [r["id"] for r in prop["relation"]]
    elif ptype == "number":
        val = prop["number"]
    elif ptype == "checkbox":
        val = prop["checkbox"]
    elif ptype == "url":
        val = prop["url"]

    # Don't run clean_text on lists (relation, multi_select) — it would stringify them
    if isinstance(val, list):
        return val if len(val) > 0 else None
    return clean_text(val)

def normalize_name(name):
    if not name: return None
    # Keep alphanumeric only
    normalized = re.sub(r'[^a-zA-Z0-9]', '', name)
    if normalized and not normalized[0].isalpha():
        normalized = 'X' + normalized
    return normalized

def get_country_code_from_name(country_name):
    if not country_name: return "INT", "en"
    name_lower = country_name.lower()
    if "belgium" in name_lower: return "BE", "nl-BE"
    if "netherlands" in name_lower: return "NL", "nl-NL"
    if "denmark" in name_lower: return "DK", "da-DK"
    if "portugal" in name_lower: return "PT", "pt-PT"
    if "lithuania" in name_lower: return "LT", "lt-LT"
    return "INT", "en"

# --- Main Ontology Generation ---

def create_ontology():
    print("--- Starting FireBIM Ontology Generator ---")
    
    g = Graph()
    
    # Namespaces
    FBO = Namespace("https://ontology.firebim.be/ontology/fbo#")
    NS_MAP = {
        "BE": Namespace("https://ontology.firebim.be/ontology/fbo-BE#"),
        "NL": Namespace("https://ontology.firebim.be/ontology/fbo-NL#"),
        "DK": Namespace("https://ontology.firebim.be/ontology/fbo-DK#"),
        "PT": Namespace("https://ontology.firebim.be/ontology/fbo-PT#"),
        "LT": Namespace("https://ontology.firebim.be/ontology/fbo-LT#"),
        "INT": Namespace("https://ontology.firebim.be/ontology/fbo-INT#")
    }
    
    BOT = Namespace("https://w3id.org/bot#")
    IFC = Namespace("http://ifcowl.openbimstandards.org/IFC4#")
    
    # Bindings
    g.bind("fbo", FBO)
    g.bind("bot", BOT)
    g.bind("ifc", IFC)
    for code, ns in NS_MAP.items():
        g.bind(f"fbo-{code}", ns)
    
    g.add((FBO.FireBIMOntology, RDF.type, OWL.Ontology))
    
    # Define Core Properties
    definitions = [
        (FBO.hasDefinition, "has definition", OWL.DatatypeProperty),
        (FBO.hasISODefinition, "has ISO definition", OWL.DatatypeProperty),
        (FBO.hasUnit, "has unit", OWL.DatatypeProperty),
        (FBO.hasValueType, "has value type", OWL.DatatypeProperty),
        (FBO.hasCountryCode, "has country code", OWL.DatatypeProperty),
        (FBO.hasArticleID, "has Article ID", OWL.DatatypeProperty),
        (FBO.hasIFCEntity, "has IFC entity", OWL.DatatypeProperty),
        (FBO.isLinkedTo, "is linked to", OWL.ObjectProperty),
        (FBO.correspondsToIFC, "corresponds to IFC", OWL.ObjectProperty),
    ]
    
    for term, label, type_ in definitions:
        g.add((term, RDF.type, type_))
        g.add((term, RDFS.label, Literal(label, lang="en")))

    # 1. Load Countries Map
    countries_data = get_all_pages(DB_COUNTRIES)
    country_id_map = {}  # maps page ID -> (country_code, lang_code)
    for page in countries_data:
        # Try "Name" first, then fall back to the title field (whatever it's called)
        c_name = get_property_value(page["properties"], "Name")
        if not c_name:
            # Find the title property dynamically
            for key, val in page["properties"].items():
                if val.get("type") == "title":
                    c_name = get_property_value(page["properties"], key)
                    break
        if c_name:
            code, lang = get_country_code_from_name(c_name)
            country_id_map[page["id"]] = (code, lang)

    # 2. Load Unified Data
    unified_pages = get_all_pages(DB_UNIFIED)
    
    # 3. Indexing Phase (Map ID -> URI/Metadata)
    page_registry = {}

    for page in unified_pages:
        props = page["properties"]
        term_name = get_property_value(props, PROP_MAP["Term"])
        
        if not term_name: continue
        
        # Get Country
        rel_ids = get_property_value(props, PROP_MAP["Country"])
        c_code = "INT"
        l_code = "en"

        if isinstance(rel_ids, list) and len(rel_ids) > 0:
            cid = rel_ids[0]
            if cid in country_id_map:
                c_code, l_code = country_id_map[cid]
        
        norm_name = normalize_name(term_name)
        ns = NS_MAP.get(c_code, NS_MAP["INT"])
        
        # Determine if Class or Property
        td_type = (get_property_value(props, PROP_MAP["Type"]) or "").lower()
        td_unit = get_property_value(props, PROP_MAP["Unit"])
        td_val_type = get_property_value(props, PROP_MAP["ValueType"])
        
        # LOGIC: It is a property if explicitly stated OR if it has a Unit OR a specific Value Type
        is_prop = False
        if "property" in td_type:
            is_prop = True
        elif td_unit and td_unit != "NA":
            is_prop = True
        elif td_val_type and td_val_type != "NA":
            is_prop = True

        # Determine if this is a datatype property (has literal values) vs object property
        is_datatype_prop = False
        if is_prop and td_val_type:
            vt_lower = td_val_type.lower() if isinstance(td_val_type, str) else ""
            if any(k in vt_lower for k in ["number", "boolean", "string", "enumeration", "text"]):
                is_datatype_prop = True
        if is_prop and td_unit and td_unit != "NA":
            is_datatype_prop = True

        page_registry[page["id"]] = {
            "general_uri": URIRef(FBO[norm_name]),
            "specific_uri": URIRef(ns[norm_name]),
            "country": c_code,
            "lang": l_code,
            "is_prop": is_prop,
            "is_datatype_prop": is_datatype_prop,
            "raw_props": props # Store raw props for second pass
        }

    print(f"Indexed {len(page_registry)} entities. Generating triples...")

    # 4. Generation Phase
    for pid, meta in page_registry.items():
        s_uri = meta["specific_uri"]
        g_uri = meta["general_uri"]
        props = meta["raw_props"]
        is_prop = meta["is_prop"]
        l_code = meta["lang"]
        
        # Type Definition & Hierarchy
        if is_prop:
            prop_type = OWL.DatatypeProperty if meta["is_datatype_prop"] else OWL.ObjectProperty
            g.add((g_uri, RDF.type, prop_type))
            g.add((s_uri, RDF.type, prop_type))
            g.add((s_uri, RDFS.subPropertyOf, g_uri))
        else:
            g.add((g_uri, RDF.type, OWL.Class))
            g.add((s_uri, RDF.type, OWL.Class))
            g.add((s_uri, RDFS.subClassOf, g_uri))
            g.add((g_uri, RDFS.subClassOf, BOT.Element))

        # Labels
        name_en = get_property_value(props, PROP_MAP["Name_EN"])
        if name_en:
            g.add((g_uri, RDFS.label, Literal(name_en, lang="en")))
            g.add((s_uri, RDFS.label, Literal(name_en, lang="en")))
            
        name_native = get_property_value(props, PROP_MAP["Name_Native"])
        if name_native and meta["country"] != "INT":
            g.add((s_uri, RDFS.label, Literal(name_native, lang=l_code)))

        # Definitions (Explicit > Implicit)
        def_en = get_property_value(props, PROP_MAP["Def_Explicit_EN"]) or \
                 get_property_value(props, PROP_MAP["Def_Implicit_EN"])
        
        def_native = get_property_value(props, PROP_MAP["Def_Explicit_Nat"]) or \
                     get_property_value(props, PROP_MAP["Def_Implicit_Nat"])
        
        if def_en: g.add((s_uri, FBO.hasDefinition, Literal(def_en, lang="en")))
        if def_native: g.add((s_uri, FBO.hasDefinition, Literal(def_native, lang=l_code)))
        
        iso_def = get_property_value(props, PROP_MAP["ISO_Def"])
        if iso_def: g.add((s_uri, FBO.hasISODefinition, Literal(iso_def, lang="en")))

        # Metadata
        if meta["country"] != "INT":
            g.add((s_uri, FBO.hasCountryCode, Literal(meta["country"])))
            
        unit = get_property_value(props, PROP_MAP["Unit"])
        if unit: g.add((s_uri, FBO.hasUnit, Literal(unit)))
        
        val_t = get_property_value(props, PROP_MAP["ValueType"])
        if val_t: g.add((s_uri, FBO.hasValueType, Literal(val_t)))
        
        art_id = get_property_value(props, PROP_MAP["ArticleID"])
        if art_id: g.add((s_uri, FBO.hasArticleID, Literal(art_id)))

        # IFC Mappings
        ifc_txt = get_property_value(props, PROP_MAP["IFC_Entity"])
        if ifc_txt:
            g.add((s_uri, FBO.hasIFCEntity, Literal(ifc_txt)))
            for part in ifc_txt.split(','):
                clean_part = part.strip().split('.')[0]
                g.add((s_uri, FBO.correspondsToIFC, URIRef(IFC[clean_part])))

        # ----------------------------------------------
        # RELATIONSHIP LOGIC
        # ----------------------------------------------
        
        # Parent / Principal Item
        parent_ids = get_property_value(props, PROP_MAP["Parent"])
        if isinstance(parent_ids, list) and parent_ids:
            for p_id in parent_ids:
                if p_id in page_registry:
                    p_uri = page_registry[p_id]["specific_uri"]
                    
                    if is_prop:
                        # If child is property, link as subProperty
                        g.add((s_uri, RDFS.subPropertyOf, p_uri))
                    else:
                        # If child is class, link as subClass
                        g.add((s_uri, RDFS.subClassOf, p_uri))
                else:
                    # Debug print if parents are missing
                    # print(f"Warning: Parent ID {p_id} not found for {s_uri}")
                    pass

        # Linked Properties (EU Terms / Harmonized)
        # Assuming this is 'seeAlso' or 'isLinkedTo' depending on semantics
        linked_ids = get_property_value(props, PROP_MAP["Linked_Props"])
        if isinstance(linked_ids, list) and linked_ids:
            for l_id in linked_ids:
                if l_id in page_registry:
                    l_uri = page_registry[l_id]["specific_uri"]
                    g.add((s_uri, FBO.isLinkedTo, l_uri))

    # Save
    outfile = "firebim_ontology_unified.ttl"
    g.serialize(destination=outfile, format="turtle")
    print(f"--- Ontology saved to {outfile} ---")

if __name__ == "__main__":
    if not NOTION_KEY:
        print("CRITICAL ERROR: NOTION_KEY is missing from .env file.")
    else:
        create_ontology()