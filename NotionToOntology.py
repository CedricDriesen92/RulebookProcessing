import os
import requests
import json
from dotenv import load_dotenv
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD
import re
# Link properties to parent properties
load_dotenv()

NOTION_KEY = os.environ.get("NOTION_KEY")

FIREBIM_PAGE = "8970296f91a94d969a1c4ecff8b83848" # https://www.notion.so/bim-kuleuven/FireBIM-Matrix-8970296f91a94d969a1c4ecff8b83848?pvs=4

DB_PROPERTIES = "d1163f8f04824d54bbfc4541fb327f06" # https://www.notion.so/bim-kuleuven/d1163f8f04824d54bbfc4541fb327f06?v=f86eec7ba67f4517bd1ce6be890d6d06&pvs=4
DB_OBJECTS = "b36b7c420df248489e165359f63d10e7" # https://www.notion.so/bim-kuleuven/b36b7c420df248489e165359f63d10e7?v=151f8487e6e7807eb099000c862b0ec6&pvs=4
DB_DOCUMENTS = "980ee046f5e04429adbcce5b02fec8aa" # https://www.notion.so/bim-kuleuven/980ee046f5e04429adbcce5b02fec8aa?v=154f8487e6e780629690000c4f86f5c3&pvs=4
DB_ARTICLES = "a6fcd8ffc7d6437cbc1bd33f77159b9e" # https://www.notion.so/bim-kuleuven/a6fcd8ffc7d6437cbc1bd33f77159b9e?v=63dcb4bf875041389ef0bdaff3161e2f&pvs=4
DB_CROSS_REF = "9519d31d657c4c3bb647fd17c4f97288" # https://www.notion.so/bim-kuleuven/9519d31d657c4c3bb647fd17c4f97288?v=103f8487e6e780ba9fae000c0fe1c48b&pvs=4
DB_RULES = "151f8487e6e780048438ffa5693dd03a" # https://www.notion.so/bim-kuleuven/151f8487e6e780048438ffa5693dd03a?v=a4470c7db86e4216a0e960fbd556d8d4&pvs=4
DB_FLOWCHARTS = "153f8487e6e7807380b0d5a9ca9723c6" # https://www.notion.so/bim-kuleuven/153f8487e6e7807380b0d5a9ca9723c6?v=cc0cb634428e4cb5990e9bb8e79b0365&pvs=4
DB_COUNTRIES = "153f8487e6e780aebc37db28dbb23feb" # https://www.notion.so/bim-kuleuven/153f8487e6e780aebc37db28dbb23feb?v=d1137671351341afa08f38517add56cd&pvs=4

headers = {'Authorization': f"Bearer {NOTION_KEY}", 
           'Content-Type': 'application/json', 
           'Notion-Version': '2022-06-28'}

def get_all_pages(database_id):
    """Get all pages from a Notion database with pagination"""
    all_pages = []
    has_more = True
    start_cursor = None
    
    while has_more:
        body = {}
        if start_cursor:
            body["start_cursor"] = start_cursor
            
        response = requests.post(
            f'https://api.notion.com/v1/databases/{database_id}/query', 
            headers=headers,
            json=body
        )
        
        data = response.json()
        all_pages.extend(data.get("results", []))
        
        has_more = data.get("has_more", False)
        if has_more:
            start_cursor = data.get("next_cursor")
    
    return all_pages

def get_rich_text_content(property_value):
    """Extract text content from rich_text property"""
    if not property_value or property_value["type"] != "rich_text" or not property_value["rich_text"]:
        return None
    
    return " ".join([text["plain_text"] for text in property_value["rich_text"]])

def get_title_content(property_value):
    """Extract text content from title property"""
    if not property_value or property_value["type"] != "title" or not property_value["title"]:
        return None
    
    return " ".join([text["plain_text"] for text in property_value["title"]])

def get_select_value(property_value):
    """Extract value from select property"""
    if not property_value or property_value["type"] != "select" or not property_value["select"]:
        return None
    
    return property_value["select"]["name"]

def get_relation_ids(property_value):
    """Extract relation IDs from relation property"""
    if not property_value or property_value["type"] != "relation":
        return []
    
    return [relation["id"] for relation in property_value["relation"]]

def normalize_name(name):
    """Normalize a name for use in a URI"""
    # Remove special characters and spaces
    normalized = re.sub(r'[^a-zA-Z0-9]', '', name)
    # Ensure first character is a letter
    if normalized and not normalized[0].isalpha():
        normalized = 'X' + normalized
    return normalized

def get_normalized_uri(name, country_code):
    """Get a normalized URI for an object or property"""
    if not name:
        return None
    normalized_name = normalize_name(name)
    return f"{normalized_name}{country_code}"

def get_country_code(props, countries_dict):
    """Get country code from language field's region part"""
    language = get_select_value(props.get("Language"))
    
    # Default international code
    country_code = "INT"
    
    # Extract region from language (which has format like "nl-BE")
    if language and "-" in language:
        parts = language.split("-")
        if len(parts) > 1:
            country_code = parts[1].upper()
    
    return country_code

def get_language_and_region(props):
    """Extract language from Language field"""
    language = get_select_value(props.get("Language"))
    
    base_lang = "en"  # Default language
    
    if language and "-" in language:
        parts = language.split("-")
        base_lang = parts[0]
    elif language:
        base_lang = language
    
    return base_lang

def create_ontology():
    # Create RDF graph
    g = Graph()
    
    # Define namespaces
    FBO = Namespace("https://ontology.firebim.be/ontology/fbo#")  # General FireBIM Building Ontology
    # Country-specific namespaces
    FBO_BE = Namespace("https://ontology.firebim.be/ontology/fbo-BE#")
    FBO_NL = Namespace("https://ontology.firebim.be/ontology/fbo-NL#")
    FBO_DK = Namespace("https://ontology.firebim.be/ontology/fbo-DK#")
    FBO_PT = Namespace("https://ontology.firebim.be/ontology/fbo-PT#")
    FBO_INT = Namespace("https://ontology.firebim.be/ontology/fbo-INT#")  # International
    
    BOT = Namespace("https://w3id.org/bot#")
    IFC = Namespace("http://ifcowl.openbimstandards.org/IFC4#")
    
    g.bind("fbo", FBO)
    g.bind("fbo-BE", FBO_BE)
    g.bind("fbo-NL", FBO_NL)
    g.bind("fbo-DK", FBO_DK)
    g.bind("fbo-PT", FBO_PT)
    g.bind("fbo-INT", FBO_INT)
    g.bind("bot", BOT)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("ifc", IFC)
    g.bind("rdf", RDF)
    
    # Create FireBIM ontology class
    g.add((FBO.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology")))
    
    # Create country-specific ontologies
    g.add((FBO_BE.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO_BE.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology - Belgium")))
    g.add((FBO_BE.FireBIMOntology, OWL.imports, FBO.FireBIMOntology))
    
    g.add((FBO_NL.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO_NL.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology - Netherlands")))
    g.add((FBO_NL.FireBIMOntology, OWL.imports, FBO.FireBIMOntology))
    
    g.add((FBO_DK.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO_DK.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology - Denmark")))
    g.add((FBO_DK.FireBIMOntology, OWL.imports, FBO.FireBIMOntology))
    
    g.add((FBO_PT.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO_PT.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology - Portugal")))
    g.add((FBO_PT.FireBIMOntology, OWL.imports, FBO.FireBIMOntology))
    
    g.add((FBO_INT.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FBO_INT.FireBIMOntology, RDFS.label, Literal("FireBIM Building Ontology - International")))
    g.add((FBO_INT.FireBIMOntology, OWL.imports, FBO.FireBIMOntology))
    
    # Define all custom properties in the ontology
    print("Defining ontology properties...")
    
    # Define isLinkedTo property (bidirectional with hasProperty)
    g.add((FBO.isLinkedTo, RDF.type, OWL.ObjectProperty))
    g.add((FBO.isLinkedTo, RDFS.label, Literal("is linked to", lang="en")))
    g.add((FBO.isLinkedTo, RDFS.comment, Literal("Links a property to an object it describes", lang="en")))
    g.add((FBO.isLinkedTo, OWL.inverseOf, FBO.hasProperty))
    
    # Define hasProperty property
    g.add((FBO.hasProperty, RDF.type, OWL.ObjectProperty))
    g.add((FBO.hasProperty, RDFS.label, Literal("has property", lang="en")))
    g.add((FBO.hasProperty, RDFS.comment, Literal("Links an object to a property that describes it", lang="en")))
    
    # Define hasDefinition property
    g.add((FBO.hasDefinition, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasDefinition, RDFS.label, Literal("has definition", lang="en")))
    g.add((FBO.hasDefinition, RDFS.comment, Literal("Links an entity to its definition", lang="en")))
    
    # Define hasISODefinition property
    g.add((FBO.hasISODefinition, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasISODefinition, RDFS.label, Literal("has ISO definition", lang="en")))
    g.add((FBO.hasISODefinition, RDFS.comment, Literal("Links an entity to its ISO definition", lang="en")))
    g.add((FBO.hasISODefinition, RDFS.subPropertyOf, FBO.hasDefinition))
    
    # Define hasUnit property
    g.add((FBO.hasUnit, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasUnit, RDFS.label, Literal("has unit", lang="en")))
    g.add((FBO.hasUnit, RDFS.comment, Literal("Specifies the unit of measurement for a property", lang="en")))
    
    # Define hasDomain property
    g.add((FBO.hasDomain, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasDomain, RDFS.label, Literal("has domain", lang="en")))
    g.add((FBO.hasDomain, RDFS.comment, Literal("Specifies the domain an entity belongs to", lang="en")))
    
    # Define hasRemark property
    g.add((FBO.hasRemark, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasRemark, RDFS.label, Literal("has remark", lang="en")))
    g.add((FBO.hasRemark, RDFS.comment, Literal("Additional remarks about an entity", lang="en")))
    
    # Define hasType property
    g.add((FBO.hasType, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasType, RDFS.label, Literal("has type", lang="en")))
    g.add((FBO.hasType, RDFS.comment, Literal("Specifies the type of a property", lang="en")))
    
    # Define hasValueType property
    g.add((FBO.hasValueType, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasValueType, RDFS.label, Literal("has value type", lang="en")))
    g.add((FBO.hasValueType, RDFS.comment, Literal("Specifies the data type of a property's value", lang="en")))
    
    # Define hasCountryCode property
    g.add((FBO.hasCountryCode, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasCountryCode, RDFS.label, Literal("has country code", lang="en")))
    g.add((FBO.hasCountryCode, RDFS.comment, Literal("Specifies the country an entity is associated with", lang="en")))
    
    # Define hasRegion property
    g.add((FBO.hasRegion, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasRegion, RDFS.label, Literal("has region", lang="en")))
    g.add((FBO.hasRegion, RDFS.comment, Literal("Specifies the region within a country", lang="en")))
    
    # Define hasIFCEntity property
    g.add((FBO.hasIFCEntity, RDF.type, OWL.DatatypeProperty))
    g.add((FBO.hasIFCEntity, RDFS.label, Literal("has IFC entity", lang="en")))
    g.add((FBO.hasIFCEntity, RDFS.comment, Literal("Specifies the IFC entity name", lang="en")))
    
    # Define correspondsToIFC property
    g.add((FBO.correspondsToIFC, RDF.type, OWL.ObjectProperty))
    g.add((FBO.correspondsToIFC, RDFS.label, Literal("corresponds to IFC", lang="en")))
    g.add((FBO.correspondsToIFC, RDFS.comment, Literal("Links to the corresponding IFC entity", lang="en")))
    
    # Define hasISOTermLink property
    g.add((FBO.hasISOTermLink, RDF.type, OWL.ObjectProperty))
    g.add((FBO.hasISOTermLink, RDFS.label, Literal("has ISO term link", lang="en")))
    g.add((FBO.hasISOTermLink, RDFS.comment, Literal("Links to the ISO term definition", lang="en")))
    
    # Define hasBSDDLink property
    g.add((FBO.hasBSDDLink, RDF.type, OWL.ObjectProperty))
    g.add((FBO.hasBSDDLink, RDFS.label, Literal("has bSDD link", lang="en")))
    g.add((FBO.hasBSDDLink, RDFS.comment, Literal("Links to the buildingSMART Data Dictionary entry", lang="en")))
    
    # Define hasBIMidsLink property
    g.add((FBO.hasBIMidsLink, RDF.type, OWL.ObjectProperty))
    g.add((FBO.hasBIMidsLink, RDFS.label, Literal("has BIMids link", lang="en")))
    g.add((FBO.hasBIMidsLink, RDFS.comment, Literal("Links to the BIMids.eu entry", lang="en")))
    
    # First, get all countries to use for URI creation
    print("Fetching countries data...")
    countries_pages = get_all_pages(DB_COUNTRIES)
    countries_dict = {}
    
    for country_page in countries_pages:
        country_id = country_page["id"]
        country_props = country_page["properties"]
        country_name = get_title_content(country_props.get("Name"))
        if country_name:
            countries_dict[country_id] = country_name
    
    print(f"Found {len(countries_dict)} countries")
    # Add a print statement to show all countries
    print("Countries in the project:", sorted(list(countries_dict.values())))
    
    # Function to get the appropriate namespace based on country code
    def get_country_namespace(country_code):
        if country_code == "BE":
            return FBO_BE
        elif country_code == "NL":
            return FBO_NL
        elif country_code == "DK":
            return FBO_DK
        elif country_code == "PT":
            return FBO_PT
        else:
            return FBO_INT
    
    # First pass: Create a mapping of object IDs to their URIs and collect parent-child relationships
    print("Building object URI mapping...")
    object_id_to_uri = {}
    object_name_to_uri = {}
    object_id_to_general_uri = {}  # Map to store the general concept URI for each object
    parent_child_relations = {}  # Store parent-child relationships
    subitem_relations = {}       # Store sub-item relationships
    
    # First, collect all objects and create both general and country-specific URIs
    for page in get_all_pages(DB_OBJECTS):
        object_id = page["id"]
        props = page["properties"]
        name_en = get_title_content(props.get("Name"))
        
        if not name_en:
            continue
            
        # Get country code from language field
        country_code = get_country_code(props, countries_dict)
        
        # Create normalized name (without country code)
        normalized_name = normalize_name(name_en)
        
        # Create general concept URI (in the FBO namespace)
        general_uri = URIRef(FBO[normalized_name])
        
        # Create country-specific URI in the appropriate namespace
        country_ns = get_country_namespace(country_code)
        country_uri = URIRef(country_ns[normalized_name])
        
        # Store in mappings
        object_id_to_uri[object_id] = country_uri
        object_id_to_general_uri[object_id] = general_uri
        object_name_to_uri[name_en.lower()] = country_uri
        
        # Collect parent-child relationships
        parent_ids = get_relation_ids(props.get("Parent item"))
        if parent_ids:
            parent_child_relations[object_id] = parent_ids
        
        # Collect sub-item relationships
        subitem_ids = get_relation_ids(props.get("Sub-item"))
        if subitem_ids:
            subitem_relations[object_id] = subitem_ids
    
    print(f"Built mapping for {len(object_id_to_uri)} objects")
    
    # Process properties
    print("Fetching properties data...")
    properties_pages = get_all_pages(DB_PROPERTIES)
    print(f"Found {len(properties_pages)} properties")
    
    for page in properties_pages:
        props = page["properties"]
        
        # Get property name
        name_en = get_rich_text_content(props.get("Name (English)"))
        if not name_en:
            continue
        
        # Get country code from language field
        country_code = get_country_code(props, countries_dict)
        
        # Get language only (no region)
        language = get_language_and_region(props)
        
        # Create normalized property name
        normalized_name = normalize_name("property_" + name_en)
        
        # Create general property URI
        general_property_uri = URIRef(FBO[normalized_name])
        
        # Create country-specific property URI
        country_ns = get_country_namespace(country_code)
        property_uri = URIRef(country_ns[normalized_name])
        
        # Add general property to ontology
        g.add((general_property_uri, RDF.type, OWL.ObjectProperty))
        g.add((general_property_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # Add country-specific property as subproperty of general property
        g.add((property_uri, RDF.type, OWL.ObjectProperty))
        g.add((property_uri, RDFS.subPropertyOf, general_property_uri))
        g.add((property_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # Add native language name if available
        name_native = get_rich_text_content(props.get("Name (native language)"))
        if name_native:
            g.add((property_uri, RDFS.label, Literal(name_native, lang=language)))
        
        # Add definitions with appropriate language tags directly to the property
        definition_en = get_rich_text_content(props.get("Definition (English)"))
        if definition_en:
            g.add((property_uri, FBO.hasDefinition, Literal(definition_en, lang="en")))
        
        definition_native = get_rich_text_content(props.get("Definition (Native Language)"))
        if definition_native:
            g.add((property_uri, FBO.hasDefinition, Literal(definition_native, lang=language)))
        
        # Add unit if available
        unit = get_rich_text_content(props.get("Unit"))
        if unit:
            g.add((property_uri, FBO.hasUnit, Literal(unit)))
        
        # Add domain if available
        domain = get_rich_text_content(props.get("Domain"))
        if domain:
            g.add((property_uri, FBO.hasDomain, Literal(domain)))
        
        # Add remark if available
        remark = get_rich_text_content(props.get("Remark"))
        if remark:
            g.add((property_uri, FBO.hasRemark, Literal(remark)))
        
        # Add type information
        prop_type = get_select_value(props.get("Type"))
        if prop_type:
            g.add((property_uri, FBO.hasType, Literal(prop_type)))
        
        # Add value type if available
        value_type = get_select_value(props.get("Value"))
        if value_type:
            g.add((property_uri, FBO.hasValueType, Literal(value_type)))
        
        # Add "property is linked to" relationships
        linked_object_ids = get_relation_ids(props.get("Property is linked to"))
        for linked_id in linked_object_ids:
            if linked_id in object_id_to_uri:
                linked_uri = object_id_to_uri[linked_id]
                g.add((property_uri, FBO.isLinkedTo, linked_uri))
        
        # Add country information
        if country_code != "INT":
            g.add((property_uri, FBO.hasCountryCode, Literal(country_code)))
    
    # Process objects - first pass to assign BOT types to top-level objects
    print("Fetching objects data...")
    objects_pages = get_all_pages(DB_OBJECTS)
    print(f"Found {len(objects_pages)} objects")

    # We'll track which objects have been assigned a BOT type
    objects_with_bot_type = set()
    
    # Store object tags for inheritance
    object_id_to_tags = {}

    # First pass: Process all objects and assign BOT types to top-level objects
    for page in objects_pages:
        props = page["properties"]
        object_id = page["id"]
        
        # Get object name from title field
        name_en = get_title_content(props.get("Name"))
        if not name_en:
            continue
        
        # Store tags for each object
        tags = get_select_value(props.get("Tags"))
        object_id_to_tags[object_id] = tags
        
        # Get country code from language field
        country_code = get_country_code(props, countries_dict)
        
        # Get the normalized name
        normalized_name = normalize_name(name_en)
        
        # Get the general and country-specific URIs
        general_uri = object_id_to_general_uri[object_id]
        country_uri = object_id_to_uri[object_id]
        
        # Add country information if not international
        if country_code != "INT":
            g.add((country_uri, FBO.hasCountryCode, Literal(country_code)))
        
        # Check if this is a top-level object (no parent)
        is_top_level = object_id not in [child_id for child_ids in parent_child_relations.values() for child_id in child_ids]
        is_top_level = is_top_level and object_id not in [subitem_id for subitem_ids in subitem_relations.values() for subitem_id in subitem_ids]
        
        # For general concepts, use RDF.type to connect to BOT.Zone or BOT.Element
        g.add((general_uri, RDF.type, OWL.Class))
        
        # Determine object type based on Tags
        if tags and "spatial" in tags.lower():
            g.add((general_uri, RDFS.subClassOf, BOT.Zone))
        else:
            g.add((general_uri, RDFS.subClassOf, BOT.Element))
        
        # Add label to general concept
        g.add((general_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # For country-specific concepts, make them subclasses of the general concept
        g.add((country_uri, RDF.type, OWL.Class))
        g.add((country_uri, RDFS.subClassOf, general_uri))
        g.add((country_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # Mark this object as having a BOT type assigned
        objects_with_bot_type.add(object_id)
        
        # Add ISO definition with language tag
        iso_definition = get_rich_text_content(props.get("ISO Definition"))
        if iso_definition:
            g.add((country_uri, FBO.hasISODefinition, Literal(iso_definition, lang="en")))
        
        # Add English definition with language tag
        definition_en = get_rich_text_content(props.get("Definition (English)"))
        if definition_en:
            g.add((country_uri, FBO.hasDefinition, Literal(definition_en, lang="en")))
        
        # Add native definition with language tag
        definition_native = get_rich_text_content(props.get("Definition (Native Language)"))
        if definition_native:
            # Determine the language tag based on the country code
            lang_tag = "en"  # default to English if no country code is found
            if country_code == "DK":
                lang_tag = "dk"
            elif country_code == "PT":
                lang_tag = "pt"
            elif country_code == "BE":
                lang_tag = "nl-BE"
            elif country_code == "NL":
                lang_tag = "nl-NL"
            
            g.add((country_uri, FBO.hasDefinition, Literal(definition_native, lang=lang_tag)))
        
        # Add IFC mapping if available
        ifc_entity = get_rich_text_content(props.get("Entity (IFC4)"))
        if ifc_entity:
            g.add((country_uri, FBO.hasIFCEntity, Literal(ifc_entity)))
            
            # Handle multiple IFC entities (comma-separated)
            ifc_entities = [e.strip() for e in ifc_entity.split(',')]
            for entity in ifc_entities:
                # Extract the base class (before any dot)
                ifc_class = entity.split('.')[0] if '.' in entity else entity
                # Create a reference to the IFC entity
                ifc_ref = URIRef(IFC[ifc_class])
                g.add((country_uri, FBO.correspondsToIFC, ifc_ref))
        
        # Add ISO Term link if available
        iso_term_url = props.get("ISO Term", {}).get("url")
        if iso_term_url:
            g.add((country_uri, FBO.hasISOTermLink, URIRef(iso_term_url)))
        
        # Add bSDD link if available
        bsdd_url = props.get("bSDD", {}).get("url")
        if bsdd_url:
            g.add((country_uri, FBO.hasBSDDLink, URIRef(bsdd_url)))
        
        # Add BIMids.eu link if available
        bimids_url = props.get("BIMids.eu", {}).get("url")
        if bimids_url:
            g.add((country_uri, FBO.hasBIMidsLink, URIRef(bimids_url)))
        
        # Add remark if available
        remark = get_rich_text_content(props.get("Remark"))
        if remark:
            g.add((country_uri, FBO.hasRemark, Literal(remark)))
    
    # Process parent-child relationships
    for child_id, parent_ids in parent_child_relations.items():
        if child_id in object_id_to_uri:
            child_country_uri = object_id_to_uri[child_id]
            child_general_uri = object_id_to_general_uri[child_id]
            
            # If child has no tags, inherit from parent
            if not object_id_to_tags.get(child_id) and parent_ids:
                for parent_id in parent_ids:
                    parent_tags = object_id_to_tags.get(parent_id)
                    if parent_tags:
                        # Assign parent tags to child
                        object_id_to_tags[child_id] = parent_tags
                        break
            
            for parent_id in parent_ids:
                if parent_id in object_id_to_uri:
                    parent_country_uri = object_id_to_uri[parent_id]
                    parent_general_uri = object_id_to_general_uri[parent_id]
                    
                    # For general concepts, establish parent-child relationship
                    g.add((child_general_uri, RDFS.subClassOf, parent_general_uri))
                    
                    # For country-specific concepts, establish parent-child relationship
                    # (in addition to being subclasses of their general concepts)
                    g.add((child_country_uri, RDFS.subClassOf, parent_country_uri))

    # Save the ontology to a file
    g.serialize(destination="buildingontologies/firebim_ontology_notion.ttl", format="turtle")
    print("Ontology saved to buildingontologies/firebim_ontology_notion.ttl")

if __name__ == "__main__":
    create_ontology()