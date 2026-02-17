import os
import requests
from dotenv import load_dotenv
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD, SKOS
import re
from collections import Counter

# --- Configuration ---
load_dotenv()
NOTION_KEY = os.environ.get("NOTION_KEY")

# Database IDs
DB_UNIFIED = "d1163f8f04824d54bbfc4541fb327f06"
DB_COUNTRIES = "153f8487e6e780aebc37db28dbb23feb"

# NOTION PROPERTY NAMES MAPPING
PROP_MAP = {
    # TM - Column to maintain
    "Term": "TM - Harmonized Term",                    # title
    "Name_EN": "TM - Name (English)",                  # rich_text
    "Name_Native": "TM - Name (native language)",      # rich_text
    "Designators": "TM - Designators",                 # rich_text
    "EquivalentTerm": "TM - Equivalent Term",          # rich_text
    "Remarks_TM": "TM - Remarks",                      # rich_text
    "FB_Documents": "TM - FB:documents",               # relation
    # TC - new column and need to be completed
    "AdoptedDefinition": "TC - Adopted definition",     # select
    "ArticleID": "TC - Article ID (it depends of the country)",  # rich_text
    "Def_Explicit_EN": "TC - Explicit Definition (English)",     # rich_text
    "Def_Explicit_Nat": "TC - Explicit Definition (Native Language) ",  # rich_text (trailing space)
    "Def_Implicit_EN": "TC - Implicit Definition  (English)",   # rich_text (double space)
    "Def_Implicit_Nat": "TC - Implicit Definition  (Native Language)", # rich_text
    "Def_Expert_EN": "TC - Expert Definition (English)",         # rich_text
    "Def_Expert_Nat": "TC - Expert Definition (Native Language))",  # rich_text (double paren lol)
    "FB_Domains": "TC - FB:Domains",                   # relation
    "FireExpertEntity": "TC - Fire Expert Entity",     # rich_text
    "FireExpertGuidance": "TC - Fire Expert Guidance", # rich_text
    "LastEdition": "TC - Last Edition",                # date
    "FireExpertValidation": "TM - Fire Expert Validation",  # select/checkbox
    # TD - column for discussion
    "Type": "TD - Type",                               # select
    "Unit": "TD - Unit",                               # rich_text
    "ValueType": "TD - Value",                         # rich_text
    "IFC_Entity": "TD - IFC Entity",                   # rich_text
    "IFC_Comment": "TD - Comment IFC",                 # rich_text
    "IFC_Mapping": "TD - Mapping IFC",                 # rich_text
    # TR - column to be replaced and deleted from this page
    "ISO_Def": "TR - ISO definition",                  # rich_text
    "TR_Code": "TR - Code",                            # rich_text
    "TR_Def_EN": "TR - Definition (English)",          # rich_text
    "TR_Def_Nat": "TR - Definition (Native Language)", # rich_text
    "TR_Derivation": "TR - Derivation",                # rich_text
    "TR_Domain": "TR - Domain",                        # rich_text
    "TR_Domains": "TR - Domains",                      # rich_text
    "TR_InterpretationLevel": "TR - Interpretation level",  # rich_text
    "TR_Language": "TR - Language",                     # rich_text
    "TR_Remarks": "TR - Remarks",                      # rich_text
    "TR_SOTermIRI": "TR - SO Term IRI",                # url
    "TR_Status": "TR - Status",                        # select
    "FB_Articles": "TR - FB:articles",                 # relation
    "FB_Articles_WIP": "TR - FB:articles (WIP)",       # relation
    # Unique ID
    "UniqueID": "ID",                                  # unique_id
    # Relations
    "Country": "Country",                              # relation
    "Parent": "item principal",                        # relation
    "Linked_Props": "Property is linked to EU terms or other Harmonized Terms",  # relation
    "Related_Props": "Related FB:properties",          # relation
    "Subitem": "Subitem",                              # relation
}

headers = {
    'Authorization': f"Bearer {NOTION_KEY}",
    'Content-Type': 'application/json',
    'Notion-Version': '2022-06-28'
}

# Country name -> (code, language tag)
COUNTRY_INFO = {
    "belgium": ("BE", "nl-BE"),
    "netherlands": ("NL", "nl-NL"),
    "denmark": ("DK", "da-DK"),
    "portugal": ("PT", "pt-PT"),
    "lithuania": ("LT", "lt-LT"),
}

# --- Helpers ---

def clean_text(text):
    """Remove NA, N/A, and trim whitespace. Only for scalar values."""
    if text is None:
        return None
    t = str(text).strip()
    if t.upper() in ["NA", "N/A", "NONE", "NULL", ""]:
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

def get_page_title(page_id):
    """Fetch a single page's title from Notion (for resolving cross-DB relations)."""
    try:
        response = requests.get(
            f'https://api.notion.com/v1/pages/{page_id}',
            headers=headers
        )
        response.raise_for_status()
        props = response.json().get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title" and prop.get("title"):
                return "".join([t["plain_text"] for t in prop["title"]])
    except Exception:
        pass
    return None

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

    if ptype == "title" and prop["title"]:
        return clean_text("".join([t["plain_text"] for t in prop["title"]]))
    elif ptype == "rich_text" and prop["rich_text"]:
        return clean_text("".join([t["plain_text"] for t in prop["rich_text"]]))
    elif ptype == "select" and prop["select"]:
        return clean_text(prop["select"]["name"])
    elif ptype == "multi_select":
        vals = [item["name"] for item in prop["multi_select"]]
        return vals if vals else None
    elif ptype == "relation":
        vals = [r["id"] for r in prop["relation"]]
        return vals if vals else None
    elif ptype == "number":
        return prop["number"]
    elif ptype == "checkbox":
        return prop["checkbox"]
    elif ptype == "url":
        return clean_text(prop["url"])
    elif ptype == "date" and prop["date"]:
        return prop["date"].get("start")
    elif ptype == "last_edited_time":
        return prop.get("last_edited_time")
    elif ptype == "unique_id" and prop.get("unique_id"):
        uid = prop["unique_id"]
        prefix = uid.get("prefix")
        number = uid.get("number")
        if prefix:
            return f"{prefix}-{number}"
        return str(number) if number is not None else None

    return None

def normalize_name(name):
    if not name: return None
    normalized = re.sub(r'[^a-zA-Z0-9]', '', name)
    if not normalized: return None
    if not normalized[0].isalpha():
        normalized = 'X' + normalized
    return normalized

def get_country_info(country_name):
    """Get country code and language tag from country name."""
    if not country_name:
        return "INT", "en"
    name_lower = country_name.lower()
    for key, (code, lang) in COUNTRY_INFO.items():
        if key in name_lower:
            return code, lang
    return "INT", "en"

def resolve_relation_titles(relation_ids, page_registry, title_cache):
    """Resolve relation IDs to titles. Uses page_registry for same-DB, fetches for cross-DB."""
    titles = []
    for rid in relation_ids:
        if rid in page_registry:
            # Same database - use the term name from raw_props
            name = get_property_value(page_registry[rid]["raw_props"], PROP_MAP["Term"])
            if name:
                titles.append(name)
        elif rid in title_cache:
            titles.append(title_cache[rid])
        else:
            title = get_page_title(rid)
            if title:
                title_cache[rid] = title
                titles.append(title)
    return titles

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

    # BOT class mapping for general URIs (only applied to owl:Class).
    # Two-pass matching: first exact name, then substring.
    # avoids false positives like "BuildingInternalWall" subclassed to bot:Building.
    BOT_EXACT = {
        # bot:Site — land/plot level
        "site": BOT.Site,
        "neighbouringplot": BOT.Site,
        "buildingplotboundary": BOT.Site,
        "adjoiningterrain": BOT.Site,
        "publicroad": BOT.Site,
        "publicgreen": BOT.Site,
        "publicwater": BOT.Site,
        # bot:Building — whole-building level
        "building": BOT.Building,
        "buildingresidential": BOT.Building,
        "highrisebuilding": BOT.Building,
        "lowrisebuilding": BOT.Building,
        "miderisebuilding": BOT.Building,
        "mediumrisebuilding": BOT.Building,
        "verytallbuilding": BOT.Building,
        "independentbuilding": BOT.Building,
        # bot:Storey — floor/storey level
        "buildinglayer": BOT.Storey,
        "buildinglayers": BOT.Storey,
        "buildinglayerparking": BOT.Storey,
        "buildingstorey": BOT.Storey,
        "evacuationlevel": BOT.Storey,
        "lowestevacuationlevel": BOT.Storey,
        "level": BOT.Storey,
        "measurementlevel": BOT.Storey,
        "countablebuildingstorey": BOT.Storey,
        "connectingbuildingstoreys": BOT.Storey,
        # bot:Element — specific compound terms that contain "building" but are elements
        "buildinginternalwall": BOT.Element,
        "buildingpartitionconstructionexternal": BOT.Element,
        "buildingfirecompartmentdaytimeoccupancy": BOT.Space,
        "buildingfunctionalfireunit": BOT.Space,
    }

    # Substring keywords — used when no exact match is found.
    # Order matters: first match wins.
    BOT_KEYWORDS = [
        # bot:Space — rooms, compartments, enclosed spatial zones
        (BOT.Space, [
            "firecompartment", "subcompartment", "compartment",
            "room", "space", "cell", "dwelling",
            "atrium", "duplex", "triplex",
            "enclosedspace", "lobby",
            "parking", "elevator", "liftcage",
            "tunnel", "accomodation",
            "commonarea", "livingunit",
        ]),
        # bot:Element — physical building components and products
        (BOT.Element, [
            "wall", "door", "ceiling", "floor", "slab", "roof",
            "duct", "conduit", "pipe", "shaft",
            "stair", "ramp",
            "window", "opening", "covering", "cladding",
            "barrier", "cable",
            "rainscreen", "facade",
            "supportingstructure", "structuralcomponent",
            "smokevent", "smokebarrier", "smokescreens",
            "smokecontrol", "smokeandheat",
        ]),
    ]

    def get_bot_class(norm_name):
        """Return the BOT superclass for a normalized concept name, or None."""
        name_lower = norm_name.lower()
        # 1. Exact match on full normalized name
        if name_lower in BOT_EXACT:
            return BOT_EXACT[name_lower]
        # 2. Substring keyword match
        for bot_cls, keywords in BOT_KEYWORDS:
            for kw in keywords:
                if kw in name_lower:
                    return bot_cls
        return None

    # Bindings
    g.bind("fbo", FBO)
    g.bind("bot", BOT)
    g.bind("ifc", IFC)
    g.bind("skos", SKOS)
    for code, ns in NS_MAP.items():
        g.bind(f"fbo-{code}", ns)

    g.add((FBO.FireBIMOntology, RDF.type, OWL.Ontology))

    # Define Core Properties — Datatype Properties
    datatype_props = [
        (FBO.hasDefinition, "has definition"),
        (FBO.hasExpertDefinition, "has expert definition"),
        (FBO.hasReferenceDefinition, "has reference definition"),
        (FBO.hasISODefinition, "has ISO definition"),
        (FBO.hasUnit, "has unit"),
        (FBO.hasValueType, "has value type"),
        (FBO.hasCountryCode, "has country code"),
        (FBO.hasArticleID, "has Article ID"),
        (FBO.hasIFCEntity, "has IFC entity"),
        (FBO.hasIFCMapping, "has IFC mapping"),
        (FBO.hasIFCComment, "has IFC comment"),
        (FBO.hasDesignator, "has designator"),
        (FBO.hasEquivalentTerm, "has equivalent term"),
        (FBO.hasDerivation, "has derivation"),
        (FBO.hasDomain, "has domain"),
        (FBO.hasInterpretationLevel, "has interpretation level"),
        (FBO.hasLanguage, "has language"),
        (FBO.hasReferenceCode, "has reference code"),
        (FBO.hasStatus, "has status"),
        (FBO.hasAdoptedDefinitionType, "has adopted definition type"),
        (FBO.hasFireExpertEntity, "has fire expert entity"),
        (FBO.hasFireExpertGuidance, "has fire expert guidance"),
        (FBO.hasRemarks, "has remarks"),
        (FBO.hasLastEdition, "has last edition date"),
        (FBO.hasFireExpertValidation, "has fire expert validation"),
        (FBO.hasNotionID, "has Notion unique identifier"),
    ]

    object_props = [
        (FBO.isLinkedTo, "is linked to"),
        (FBO.correspondsToIFC, "corresponds to IFC"),
        (FBO.hasRelatedProperty, "has related property"),
        (FBO.hasSubitem, "has subitem"),
        (FBO.hasCountry, "has country"),
        (FBO.hasDomainReference, "has domain reference"),
        (FBO.hasDocumentReference, "has document reference"),
        (FBO.hasArticleReference, "has article reference"),
        (FBO.hasNotionURL, "has Notion page URL"),
    ]

    for term, label in datatype_props:
        g.add((term, RDF.type, OWL.DatatypeProperty))
        g.add((term, RDFS.label, Literal(label, lang="en")))

    for term, label in object_props:
        g.add((term, RDF.type, OWL.ObjectProperty))
        g.add((term, RDFS.label, Literal(label, lang="en")))

    # Define reference category classes
    for cls, label in [
        (FBO.Country, "Country"),
        (FBO.RegulatoryDomain, "Regulatory Domain"),
        (FBO.Document, "Document"),
        (FBO.Article, "Article"),
    ]:
        g.add((cls, RDF.type, OWL.Class))
        g.add((cls, RDFS.label, Literal(label, lang="en")))

    # 1. Load Countries Map & create Country instances
    countries_data = get_all_pages(DB_COUNTRIES)
    country_id_map = {}    # Notion page ID -> country code
    country_lang_map = {}  # Notion page ID -> language tag
    country_uri_map = {}   # Notion page ID -> country URI
    for page in countries_data:
        c_name = get_property_value(page["properties"], "Name")
        if c_name:
            code, lang = get_country_info(c_name)
            country_id_map[page["id"]] = code
            country_lang_map[page["id"]] = lang
            # Create Country instance in ontology
            norm = normalize_name(c_name)
            if norm:
                c_uri = URIRef(FBO[norm])
                country_uri_map[page["id"]] = c_uri
                g.add((c_uri, RDF.type, FBO.Country))
                g.add((c_uri, RDFS.label, Literal(c_name, lang="en")))
                g.add((c_uri, FBO.hasCountryCode, Literal(code)))

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

        if rel_ids and len(rel_ids) > 0:
            cid = rel_ids[0]
            if cid in country_id_map:
                c_code = country_id_map[cid]
                l_code = country_lang_map[cid]

        norm_name = normalize_name(term_name)
        if not norm_name: continue
        ns = NS_MAP.get(c_code, NS_MAP["INT"])

        # Determine OWL type: Class, ObjectProperty, or DatatypeProperty
        # Only use TD - Type column to decide; unit/valueType alone don't make something a property
        td_type = str(get_property_value(props, PROP_MAP["Type"]) or "").lower().strip()
        td_unit = get_property_value(props, PROP_MAP["Unit"])
        td_val_type = str(get_property_value(props, PROP_MAP["ValueType"]) or "").lower().strip()

        DATATYPE_VALUES = ["number", "boolean (yes/no)", "boolean", "enumeration (choice)",
                           "enumeration", "string", "text", "integer", "float", "date"]

        if td_type == "property" and (td_unit or td_val_type in DATATYPE_VALUES):
            # Explicitly property with a unit or datatype value → DatatypeProperty
            owl_type = "datatype_property"
        elif td_type == "property":
            # Explicitly property but no unit/datatype indicators → ObjectProperty
            owl_type = "object_property"
        else:
            # Default (including td_type == "object" or empty): treat as Class
            owl_type = "class"

        # Resolve country URIs for this entity
        country_uris = []
        if rel_ids:
            for cid in rel_ids:
                if cid in country_uri_map:
                    country_uris.append(country_uri_map[cid])

        page_registry[page["id"]] = {
            "general_uri": URIRef(FBO[norm_name]),
            "specific_uri": URIRef(ns[norm_name]),
            "country": c_code,
            "lang": l_code,
            "owl_type": owl_type,
            "country_uris": country_uris,
            "raw_props": props,
            "notion_url": page.get("url")
        }

    print(f"Indexed {len(page_registry)} entities. Generating triples...")

    # 3b. Resolve general URI types — use majority vote when countries disagree
    general_uri_votes = {}  # general_uri -> list of owl_type votes
    for meta in page_registry.values():
        g_uri = str(meta["general_uri"])
        general_uri_votes.setdefault(g_uri, []).append(meta["owl_type"])

    general_uri_type = {}  # general_uri string -> resolved owl_type
    for g_uri_str, votes in general_uri_votes.items():
        counts = Counter(votes)
        # Majority wins; on tie, prefer "class" as the safer default
        resolved = counts.most_common(1)[0][0]
        if len(counts) > 1 and counts.get("class", 0) == counts.most_common(1)[0][1]:
            resolved = "class"
        general_uri_type[g_uri_str] = resolved

    # Cache for cross-database relation title lookups
    title_cache = {}
    # Track cross-DB references by category (norm_name -> original title)
    cross_db_domains = {}
    cross_db_documents = {}
    cross_db_articles = {}
    # Track which general URIs have already been typed
    typed_general_uris = set()

    # 4. Generation Phase
    for _, meta in page_registry.items():
        s_uri = meta["specific_uri"]
        g_uri = meta["general_uri"]
        props = meta["raw_props"]
        l_code = meta["lang"]

        # Use resolved type for the general URI, and per-entry type for the specific URI
        resolved_g_type = general_uri_type[str(g_uri)]
        owl_type = meta["owl_type"]

        # Type the general URI only once, using the resolved type
        if str(g_uri) not in typed_general_uris:
            typed_general_uris.add(str(g_uri))
            if resolved_g_type == "datatype_property":
                g.add((g_uri, RDF.type, OWL.DatatypeProperty))
            elif resolved_g_type == "object_property":
                g.add((g_uri, RDF.type, OWL.ObjectProperty))
            else:
                g.add((g_uri, RDF.type, OWL.Class))
                # Add BOT superclass mapping for classes only
                norm_name = str(g_uri).rsplit('#', 1)[-1]
                bot_cls = get_bot_class(norm_name)
                if bot_cls:
                    g.add((g_uri, RDFS.subClassOf, bot_cls))

        # Type the specific (country) URI — follow the resolved general type
        # so that subClassOf/subPropertyOf is consistent
        if resolved_g_type == "datatype_property":
            g.add((s_uri, RDF.type, OWL.DatatypeProperty))
            g.add((s_uri, RDFS.subPropertyOf, g_uri))
        elif resolved_g_type == "object_property":
            g.add((s_uri, RDF.type, OWL.ObjectProperty))
            g.add((s_uri, RDFS.subPropertyOf, g_uri))
        else:
            g.add((s_uri, RDF.type, OWL.Class))
            g.add((s_uri, RDFS.subClassOf, g_uri))

        # --- Labels ---
        name_en = get_property_value(props, PROP_MAP["Name_EN"])
        if name_en:
            g.add((g_uri, RDFS.label, Literal(name_en, lang="en")))
            g.add((s_uri, RDFS.label, Literal(name_en, lang="en")))

        name_native = get_property_value(props, PROP_MAP["Name_Native"])
        if name_native and meta["country"] != "INT":
            g.add((s_uri, RDFS.label, Literal(name_native, lang=l_code)))

        # --- Definitions (Explicit > Implicit > Expert) ---
        def_en = get_property_value(props, PROP_MAP["Def_Explicit_EN"]) or \
                 get_property_value(props, PROP_MAP["Def_Implicit_EN"])
        def_native = get_property_value(props, PROP_MAP["Def_Explicit_Nat"]) or \
                     get_property_value(props, PROP_MAP["Def_Implicit_Nat"])

        if def_en:
            g.add((s_uri, FBO.hasDefinition, Literal(def_en, lang="en")))
        if def_native:
            g.add((s_uri, FBO.hasDefinition, Literal(def_native, lang=l_code)))

        # Expert definitions (separate property to distinguish source)
        expert_en = get_property_value(props, PROP_MAP["Def_Expert_EN"])
        expert_nat = get_property_value(props, PROP_MAP["Def_Expert_Nat"])
        if expert_en:
            g.add((s_uri, FBO.hasExpertDefinition, Literal(expert_en, lang="en")))
        if expert_nat:
            g.add((s_uri, FBO.hasExpertDefinition, Literal(expert_nat, lang=l_code)))

        # TR - Reference definitions
        tr_def_en = get_property_value(props, PROP_MAP["TR_Def_EN"])
        tr_def_nat = get_property_value(props, PROP_MAP["TR_Def_Nat"])
        if tr_def_en:
            g.add((s_uri, FBO.hasReferenceDefinition, Literal(tr_def_en, lang="en")))
        if tr_def_nat:
            g.add((s_uri, FBO.hasReferenceDefinition, Literal(tr_def_nat, lang=l_code)))

        # ISO definition
        iso_def = get_property_value(props, PROP_MAP["ISO_Def"])
        if iso_def:
            g.add((s_uri, FBO.hasISODefinition, Literal(iso_def, lang="en")))

        # Adopted definition type (e.g. "Explicit definition", "Expert definition")
        adopted = get_property_value(props, PROP_MAP["AdoptedDefinition"])
        if adopted:
            g.add((s_uri, FBO.hasAdoptedDefinitionType, Literal(adopted)))

        # --- Metadata ---
        if meta["country"] != "INT":
            g.add((s_uri, FBO.hasCountryCode, Literal(meta["country"])))
        for c_uri in meta["country_uris"]:
            g.add((s_uri, FBO.hasCountry, c_uri))

        unit = get_property_value(props, PROP_MAP["Unit"])
        if unit:
            g.add((s_uri, FBO.hasUnit, Literal(unit)))

        val_t = get_property_value(props, PROP_MAP["ValueType"])
        if val_t:
            g.add((s_uri, FBO.hasValueType, Literal(val_t)))

        art_id = get_property_value(props, PROP_MAP["ArticleID"])
        if art_id:
            g.add((s_uri, FBO.hasArticleID, Literal(art_id)))

        # Designators & Equivalent Terms
        designators = get_property_value(props, PROP_MAP["Designators"])
        if designators:
            g.add((s_uri, FBO.hasDesignator, Literal(designators)))

        equiv_term = get_property_value(props, PROP_MAP["EquivalentTerm"])
        if equiv_term:
            g.add((s_uri, FBO.hasEquivalentTerm, Literal(equiv_term)))

        # --- IFC Mappings ---
        ifc_txt = get_property_value(props, PROP_MAP["IFC_Entity"])
        if ifc_txt:
            g.add((s_uri, FBO.hasIFCEntity, Literal(ifc_txt)))
            for part in ifc_txt.split(','):
                clean_part = part.strip().split('.')[0]
                if clean_part:
                    g.add((s_uri, FBO.correspondsToIFC, URIRef(IFC[clean_part])))

        ifc_mapping = get_property_value(props, PROP_MAP["IFC_Mapping"])
        if ifc_mapping:
            g.add((s_uri, FBO.hasIFCMapping, Literal(ifc_mapping)))

        ifc_comment = get_property_value(props, PROP_MAP["IFC_Comment"])
        if ifc_comment:
            g.add((s_uri, FBO.hasIFCComment, Literal(ifc_comment)))

        # --- Reference Metadata (TR) ---
        tr_code = get_property_value(props, PROP_MAP["TR_Code"])
        if tr_code:
            g.add((s_uri, FBO.hasReferenceCode, Literal(tr_code)))

        derivation = get_property_value(props, PROP_MAP["TR_Derivation"])
        if derivation:
            g.add((s_uri, FBO.hasDerivation, Literal(derivation)))

        tr_domain = get_property_value(props, PROP_MAP["TR_Domain"])
        if tr_domain:
            g.add((s_uri, FBO.hasDomain, Literal(tr_domain)))

        tr_domains = get_property_value(props, PROP_MAP["TR_Domains"])
        if tr_domains:
            if isinstance(tr_domains, list):
                for domain in tr_domains:
                    g.add((s_uri, FBO.hasDomain, Literal(domain)))
            else:
                g.add((s_uri, FBO.hasDomain, Literal(tr_domains)))

        interp_level = get_property_value(props, PROP_MAP["TR_InterpretationLevel"])
        if interp_level:
            g.add((s_uri, FBO.hasInterpretationLevel, Literal(interp_level)))

        tr_language = get_property_value(props, PROP_MAP["TR_Language"])
        if tr_language:
            g.add((s_uri, FBO.hasLanguage, Literal(tr_language)))

        tr_status = get_property_value(props, PROP_MAP["TR_Status"])
        if tr_status:
            g.add((s_uri, FBO.hasStatus, Literal(tr_status)))

        so_term_iri = get_property_value(props, PROP_MAP["TR_SOTermIRI"])
        if so_term_iri:
            g.add((s_uri, SKOS.exactMatch, URIRef(so_term_iri)))

        # --- Expert Knowledge ---
        fire_entity = get_property_value(props, PROP_MAP["FireExpertEntity"])
        if fire_entity:
            g.add((s_uri, FBO.hasFireExpertEntity, Literal(fire_entity)))

        fire_guidance = get_property_value(props, PROP_MAP["FireExpertGuidance"])
        if fire_guidance:
            g.add((s_uri, FBO.hasFireExpertGuidance, Literal(fire_guidance)))

        # --- Remarks ---
        remarks_tm = get_property_value(props, PROP_MAP["Remarks_TM"])
        if remarks_tm:
            g.add((s_uri, FBO.hasRemarks, Literal(remarks_tm)))

        remarks_tr = get_property_value(props, PROP_MAP["TR_Remarks"])
        if remarks_tr:
            g.add((s_uri, FBO.hasRemarks, Literal(remarks_tr)))

        # Last Edition date
        last_edition = get_property_value(props, PROP_MAP["LastEdition"])
        if last_edition:
            g.add((s_uri, FBO.hasLastEdition, Literal(last_edition, datatype=XSD.dateTime)))

        # Fire Expert Validation
        fire_validation = get_property_value(props, PROP_MAP["FireExpertValidation"])
        if fire_validation is not None:
            # Normalize to xsd:boolean — handle string "True"/"False" and Python bools
            bool_val = str(fire_validation).strip().lower() in ("true", "1", "yes")
            g.add((s_uri, FBO.hasFireExpertValidation, Literal(bool_val, datatype=XSD.boolean)))

        # Notion Unique ID
        notion_id = get_property_value(props, PROP_MAP["UniqueID"])
        if notion_id:
            g.add((s_uri, FBO.hasNotionID, Literal(notion_id)))

        # Notion Page URL
        notion_url = meta.get("notion_url")
        if notion_url:
            g.add((s_uri, FBO.hasNotionURL, URIRef(notion_url)))

        # --- Relationships (same database) ---

        # Parent / Principal Item
        parent_ids = get_property_value(props, PROP_MAP["Parent"])
        if parent_ids:
            for p_id in parent_ids:
                if p_id in page_registry:
                    p_uri = page_registry[p_id]["specific_uri"]
                    if resolved_g_type in ("datatype_property", "object_property"):
                        g.add((s_uri, RDFS.subPropertyOf, p_uri))
                    else:
                        g.add((s_uri, RDFS.subClassOf, p_uri))

        # Linked Properties (EU Terms / Harmonized)
        linked_ids = get_property_value(props, PROP_MAP["Linked_Props"])
        if linked_ids:
            for l_id in linked_ids:
                if l_id in page_registry:
                    l_uri = page_registry[l_id]["specific_uri"]
                    g.add((s_uri, FBO.isLinkedTo, l_uri))

        # Related FB:properties
        related_ids = get_property_value(props, PROP_MAP["Related_Props"])
        if related_ids:
            for r_id in related_ids:
                if r_id in page_registry:
                    r_uri = page_registry[r_id]["specific_uri"]
                    g.add((s_uri, FBO.hasRelatedProperty, r_uri))

        # Subitems
        subitem_ids = get_property_value(props, PROP_MAP["Subitem"])
        if subitem_ids:
            for si_id in subitem_ids:
                if si_id in page_registry:
                    si_uri = page_registry[si_id]["specific_uri"]
                    g.add((s_uri, FBO.hasSubitem, si_uri))

        # --- Cross-database relations (resolved via API title lookup) ---

        # Helper to resolve, link, and track cross-DB references
        def link_cross_db(relation_key, fbo_property, category_set):
            rel_ids = get_property_value(props, PROP_MAP[relation_key])
            if rel_ids:
                titles = resolve_relation_titles(rel_ids, page_registry, title_cache)
                for title in titles:
                    norm = normalize_name(title)
                    if norm:
                        ref_uri = URIRef(FBO[norm])
                        g.add((s_uri, fbo_property, ref_uri))
                        category_set[norm] = title  # track for later definition

        link_cross_db("FB_Domains", FBO.hasDomainReference, cross_db_domains)
        link_cross_db("FB_Documents", FBO.hasDocumentReference, cross_db_documents)
        link_cross_db("FB_Articles", FBO.hasArticleReference, cross_db_articles)
        link_cross_db("FB_Articles_WIP", FBO.hasArticleReference, cross_db_articles)

    # 5. Define cross-database referenced entities as classes in the ontology
    for norm, title in cross_db_domains.items():
        uri = URIRef(FBO[norm])
        g.add((uri, RDF.type, FBO.RegulatoryDomain))
        g.add((uri, RDFS.label, Literal(title, lang="en")))

    for norm, title in cross_db_documents.items():
        uri = URIRef(FBO[norm])
        g.add((uri, RDF.type, FBO.Document))
        g.add((uri, RDFS.label, Literal(title, lang="en")))

    for norm, title in cross_db_articles.items():
        uri = URIRef(FBO[norm])
        g.add((uri, RDF.type, FBO.Article))
        g.add((uri, RDFS.label, Literal(title, lang="en")))

    print(f"  > Defined {len(cross_db_domains)} domains, {len(cross_db_documents)} documents, {len(cross_db_articles)} articles.")

    # Save
    outfile = "firebim_ontology_unified.ttl"
    g.serialize(destination=outfile, format="turtle")
    print(f"--- Ontology saved to {outfile} ({len(g)} triples) ---")
    if title_cache:
        print(f"  > Resolved {len(title_cache)} cross-database relation titles.")

if __name__ == "__main__":
    if not NOTION_KEY:
        print("CRITICAL ERROR: NOTION_KEY is missing from .env file.")
    else:
        create_ontology()
