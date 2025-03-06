import os
import requests
import json
from dotenv import load_dotenv
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD
import re

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

def get_language_and_region(props):
    """Extract language and region from Language field"""
    language = get_select_value(props.get("Language"))
    
    base_lang = "en"  # Default language
    region = None
    
    if language and "-" in language:
        parts = language.split("-")
        base_lang = parts[0]
        region = parts[1]
    elif language:
        base_lang = language
    
    return base_lang, region

def get_country_code(props, countries_dict):
    """Get country code from country relation"""
    country_ids = get_relation_ids(props.get("FB:country"))
    if not country_ids:
        return "INT"  # International/default
    
    country_id = country_ids[0]
    if country_id in countries_dict:
        country_name = countries_dict[country_id]
        # Extract 2-letter country code
        if "-" in country_name:
            return country_name.split("-")[0].upper()
    
    return "INT"  # Default if no match

def create_ontology():
    # Create RDF graph
    g = Graph()
    
    # Define namespaces
    FIREBIM = Namespace("http://example.com/firebim#")
    BOT = Namespace("https://w3id.org/bot#")
    IFC = Namespace("http://ifcowl.openbimstandards.org/IFC4#")
    
    g.bind("firebim", FIREBIM)
    g.bind("bot", BOT)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)
    g.bind("ifc", IFC)
    
    # Create FireBIM ontology class
    g.add((FIREBIM.FireBIMOntology, RDF.type, OWL.Ontology))
    g.add((FIREBIM.FireBIMOntology, RDFS.label, Literal("FireBIM Ontology")))
    
    # Define all custom properties in the ontology
    print("Defining ontology properties...")
    
    # Define isLinkedTo property (bidirectional with hasProperty)
    g.add((FIREBIM.isLinkedTo, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.isLinkedTo, RDFS.label, Literal("is linked to", lang="en")))
    g.add((FIREBIM.isLinkedTo, RDFS.comment, Literal("Links a property to an object it describes", lang="en")))
    g.add((FIREBIM.isLinkedTo, OWL.inverseOf, FIREBIM.hasProperty))
    
    # Define hasProperty property
    g.add((FIREBIM.hasProperty, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasProperty, RDFS.label, Literal("has property", lang="en")))
    g.add((FIREBIM.hasProperty, RDFS.comment, Literal("Links an object to a property that describes it", lang="en")))
    
    # Define hasDefinition property
    g.add((FIREBIM.hasDefinition, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasDefinition, RDFS.label, Literal("has definition", lang="en")))
    g.add((FIREBIM.hasDefinition, RDFS.comment, Literal("Links an entity to its definition", lang="en")))
    
    # Define hasISODefinition property
    g.add((FIREBIM.hasISODefinition, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasISODefinition, RDFS.label, Literal("has ISO definition", lang="en")))
    g.add((FIREBIM.hasISODefinition, RDFS.comment, Literal("Links an entity to its ISO definition", lang="en")))
    g.add((FIREBIM.hasISODefinition, RDFS.subPropertyOf, FIREBIM.hasDefinition))
    
    # Define hasUnit property
    g.add((FIREBIM.hasUnit, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasUnit, RDFS.label, Literal("has unit", lang="en")))
    g.add((FIREBIM.hasUnit, RDFS.comment, Literal("Specifies the unit of measurement for a property", lang="en")))
    
    # Define hasDomain property
    g.add((FIREBIM.hasDomain, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasDomain, RDFS.label, Literal("has domain", lang="en")))
    g.add((FIREBIM.hasDomain, RDFS.comment, Literal("Specifies the domain an entity belongs to", lang="en")))
    
    # Define hasRemark property
    g.add((FIREBIM.hasRemark, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasRemark, RDFS.label, Literal("has remark", lang="en")))
    g.add((FIREBIM.hasRemark, RDFS.comment, Literal("Additional remarks about an entity", lang="en")))
    
    # Define hasType property
    g.add((FIREBIM.hasType, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasType, RDFS.label, Literal("has type", lang="en")))
    g.add((FIREBIM.hasType, RDFS.comment, Literal("Specifies the type of a property", lang="en")))
    
    # Define hasValueType property
    g.add((FIREBIM.hasValueType, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasValueType, RDFS.label, Literal("has value type", lang="en")))
    g.add((FIREBIM.hasValueType, RDFS.comment, Literal("Specifies the data type of a property's value", lang="en")))
    
    # Define hasCountryCode property
    g.add((FIREBIM.hasCountryCode, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasCountryCode, RDFS.label, Literal("has country code", lang="en")))
    g.add((FIREBIM.hasCountryCode, RDFS.comment, Literal("Specifies the country an entity is associated with", lang="en")))
    
    # Define hasRegion property
    g.add((FIREBIM.hasRegion, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasRegion, RDFS.label, Literal("has region", lang="en")))
    g.add((FIREBIM.hasRegion, RDFS.comment, Literal("Specifies the region within a country", lang="en")))
    
    # Define hasIFCEntity property
    g.add((FIREBIM.hasIFCEntity, RDF.type, OWL.DatatypeProperty))
    g.add((FIREBIM.hasIFCEntity, RDFS.label, Literal("has IFC entity", lang="en")))
    g.add((FIREBIM.hasIFCEntity, RDFS.comment, Literal("Specifies the IFC entity name", lang="en")))
    
    # Define correspondsToIFC property
    g.add((FIREBIM.correspondsToIFC, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.correspondsToIFC, RDFS.label, Literal("corresponds to IFC", lang="en")))
    g.add((FIREBIM.correspondsToIFC, RDFS.comment, Literal("Links to the corresponding IFC entity", lang="en")))
    
    # Define hasISOTermLink property
    g.add((FIREBIM.hasISOTermLink, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasISOTermLink, RDFS.label, Literal("has ISO term link", lang="en")))
    g.add((FIREBIM.hasISOTermLink, RDFS.comment, Literal("Links to the ISO term definition", lang="en")))
    
    # Define hasBSDDLink property
    g.add((FIREBIM.hasBSDDLink, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasBSDDLink, RDFS.label, Literal("has bSDD link", lang="en")))
    g.add((FIREBIM.hasBSDDLink, RDFS.comment, Literal("Links to the buildingSMART Data Dictionary entry", lang="en")))
    
    # Define hasBIMidsLink property
    g.add((FIREBIM.hasBIMidsLink, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasBIMidsLink, RDFS.label, Literal("has BIMids link", lang="en")))
    g.add((FIREBIM.hasBIMidsLink, RDFS.comment, Literal("Links to the BIMids.eu entry", lang="en")))
    
    # Define parent-child relationships (bidirectional)
    g.add((FIREBIM.hasParent, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasParent, RDFS.label, Literal("has parent", lang="en")))
    g.add((FIREBIM.hasParent, RDFS.comment, Literal("Links to the parent object", lang="en")))
    g.add((FIREBIM.hasParent, OWL.inverseOf, FIREBIM.hasChild))
    
    g.add((FIREBIM.hasChild, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasChild, RDFS.label, Literal("has child", lang="en")))
    g.add((FIREBIM.hasChild, RDFS.comment, Literal("Links to a child object", lang="en")))
    
    # Define sub-item relationships (bidirectional)
    g.add((FIREBIM.hasSubItem, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.hasSubItem, RDFS.label, Literal("has sub-item", lang="en")))
    g.add((FIREBIM.hasSubItem, RDFS.comment, Literal("Links to a sub-item", lang="en")))
    
    g.add((FIREBIM.isSubItemOf, RDF.type, OWL.ObjectProperty))
    g.add((FIREBIM.isSubItemOf, RDFS.label, Literal("is sub-item of", lang="en")))
    g.add((FIREBIM.isSubItemOf, RDFS.comment, Literal("Links to the parent item", lang="en")))
    
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
    
    # First pass: Create a mapping of object IDs to their URIs and collect parent-child relationships
    print("Building object URI mapping...")
    object_id_to_uri = {}
    object_name_to_uri = {}
    parent_child_relations = {}  # Store parent-child relationships
    subitem_relations = {}       # Store sub-item relationships
    
    # First, collect all objects and their URIs
    for page in get_all_pages(DB_OBJECTS):
        object_id = page["id"]
        props = page["properties"]
        name_en = get_title_content(props.get("Name"))
        
        if not name_en:
            continue
            
        # Get country code
        country_code = get_country_code(props, countries_dict)
        
        # Create normalized URI
        uri_key = get_normalized_uri(name_en, country_code)
        uri = URIRef(FIREBIM[uri_key])
        
        # Store in mappings
        object_id_to_uri[object_id] = uri
        object_name_to_uri[name_en.lower()] = uri
        
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
        
        # Get country code - Fix for properties
        country_code = get_country_code(props, countries_dict)
        #print(f"Property: {name_en}, Country code: {country_code}")
        
        # Get language and region
        language, region = get_language_and_region(props)
        
        # Create property URI with country code
        uri_key = get_normalized_uri(name_en, country_code)
        property_uri = URIRef(FIREBIM[uri_key])
        
        # Add property to ontology
        g.add((property_uri, RDF.type, OWL.ObjectProperty))
        g.add((property_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # Add native language name if available
        name_native = get_rich_text_content(props.get("Name (native language)"))
        if name_native:
            g.add((property_uri, RDFS.label, Literal(name_native, lang=language)))
            # Add region information if available
            if region:
                g.add((property_uri, FIREBIM.hasRegion, Literal(region)))
        
        # Add definitions with appropriate language tags
        definition_en = get_rich_text_content(props.get("Definition (English)"))
        if definition_en:
            # Create a definition node with language and region information
            def_node = BNode()
            g.add((property_uri, FIREBIM.hasDefinition, def_node))
            g.add((def_node, FIREBIM.definitionText, Literal(definition_en, lang="en")))
            g.add((def_node, FIREBIM.definitionSource, Literal("FireBIM")))
        
        # Add native definition with language tag
        definition_native = get_rich_text_content(props.get("Definition (Native Language)"))
        if definition_native:
            native_def_node = BNode()
            g.add((property_uri, FIREBIM.hasDefinition, native_def_node))
            g.add((native_def_node, FIREBIM.definitionText, Literal(definition_native, lang=language)))
            g.add((native_def_node, FIREBIM.definitionSource, Literal("FireBIM")))
            if region:
                g.add((native_def_node, FIREBIM.definitionRegion, Literal(region)))
        
        # Add unit if available
        unit = get_rich_text_content(props.get("Unit"))
        if unit:
            g.add((property_uri, FIREBIM.hasUnit, Literal(unit)))
        
        # Add domain if available
        domain = get_rich_text_content(props.get("Domain"))
        if domain:
            g.add((property_uri, FIREBIM.hasDomain, Literal(domain)))
        
        # Add remark if available
        remark = get_rich_text_content(props.get("Remark"))
        if remark:
            g.add((property_uri, FIREBIM.hasRemark, Literal(remark)))
        
        # Add type information
        prop_type = get_select_value(props.get("Type"))
        if prop_type:
            g.add((property_uri, FIREBIM.hasType, Literal(prop_type)))
        
        # Add value type if available
        value_type = get_select_value(props.get("Value"))
        if value_type:
            g.add((property_uri, FIREBIM.hasValueType, Literal(value_type)))
        
        # Add country information
        if country_code != "INT":
            g.add((property_uri, FIREBIM.hasCountryCode, Literal(country_code)))
        
        # Add "property is linked to" relationships
        linked_object_ids = get_relation_ids(props.get("Property is linked to"))
        for linked_id in linked_object_ids:
            if linked_id in object_id_to_uri:
                linked_uri = object_id_to_uri[linked_id]
                g.add((property_uri, FIREBIM.isLinkedTo, linked_uri))
    
    # Process objects
    print("Fetching objects data...")
    objects_pages = get_all_pages(DB_OBJECTS)
    print(f"Found {len(objects_pages)} objects")
    
    for page in objects_pages:
        props = page["properties"]
        
        # Get object name from title field
        name_en = get_title_content(props.get("Name"))
        if not name_en:
            continue
        
        # Get country code
        country_code = get_country_code(props, countries_dict)
        
        # Create object URI with country code
        uri_key = get_normalized_uri(name_en, country_code)
        object_uri = URIRef(FIREBIM[uri_key])
        
        # Determine object type based on Tags
        tags = get_select_value(props.get("Tags"))
        
        # Default to Element, but check if it's a spatial element
        if tags and "spatial" in tags.lower():
            g.add((object_uri, RDF.type, BOT.Zone))
        else:
            g.add((object_uri, RDF.type, BOT.Element))
        
        # Add label
        g.add((object_uri, RDFS.label, Literal(name_en, lang="en")))
        
        # Add ISO definition with language tag
        iso_definition = get_rich_text_content(props.get("ISO Definition"))
        if iso_definition:
            g.add((object_uri, FIREBIM.hasISODefinition, Literal(iso_definition, lang="en")))
        
        # Add English definition with language tag
        definition_en = get_rich_text_content(props.get("Definition (English)"))
        if definition_en:
            g.add((object_uri, FIREBIM.hasDefinition, Literal(definition_en, lang="en")))
        
        # Add native definition with language tag
        definition_native = get_rich_text_content(props.get("Definition (Native Language)"))
        if definition_native:
            g.add((object_uri, FIREBIM.hasDefinition, Literal(definition_native, lang="en")))
        
        # Add IFC mapping if available
        ifc_entity = get_rich_text_content(props.get("Entity (IFC4)"))
        if ifc_entity:
            g.add((object_uri, FIREBIM.hasIFCEntity, Literal(ifc_entity)))
            
            # Handle multiple IFC entities (comma-separated)
            ifc_entities = [e.strip() for e in ifc_entity.split(',')]
            for entity in ifc_entities:
                # Extract the base class (before any dot)
                ifc_class = entity.split('.')[0] if '.' in entity else entity
                # Create a reference to the IFC entity
                ifc_ref = URIRef(IFC[ifc_class])
                g.add((object_uri, FIREBIM.correspondsToIFC, ifc_ref))
        
        # Add ISO Term link if available
        iso_term_url = props.get("ISO Term", {}).get("url")
        if iso_term_url:
            g.add((object_uri, FIREBIM.hasISOTermLink, URIRef(iso_term_url)))
        
        # Add bSDD link if available
        bsdd_url = props.get("bSDD", {}).get("url")
        if bsdd_url:
            g.add((object_uri, FIREBIM.hasBSDDLink, URIRef(bsdd_url)))
        
        # Add BIMids.eu link if available
        bimids_url = props.get("BIMids.eu", {}).get("url")
        if bimids_url:
            g.add((object_uri, FIREBIM.hasBIMidsLink, URIRef(bimids_url)))
        
        # Add remark if available
        remark = get_rich_text_content(props.get("Remark"))
        if remark:
            g.add((object_uri, FIREBIM.hasRemark, Literal(remark)))
        
        # Add country information
        if country_code != "INT":
            g.add((object_uri, FIREBIM.hasCountryCode, Literal(country_code)))
    
    # Add a second pass after processing all objects to establish the class hierarchy
    # Second pass - add parent-child and subclass relationships
    print("Processing object relationships - second pass...")
    
    # Process parent-child relationships
    for child_id, parent_ids in parent_child_relations.items():
        if child_id in object_id_to_uri:
            child_uri = object_id_to_uri[child_id]
            
            for parent_id in parent_ids:
                if parent_id in object_id_to_uri:
                    parent_uri = object_id_to_uri[parent_id]
                    
                    # Add parent-child relationship
                    g.add((child_uri, FIREBIM.hasParent, parent_uri))
                    g.add((parent_uri, FIREBIM.hasChild, child_uri))
                    
                    # Add subclass relationship - child is a subclass of parent
                    g.add((child_uri, RDFS.subClassOf, parent_uri))
    
    # Process sub-item relationships
    for item_id, subitem_ids in subitem_relations.items():
        if item_id in object_id_to_uri:
            item_uri = object_id_to_uri[item_id]
            
            for subitem_id in subitem_ids:
                if subitem_id in object_id_to_uri:
                    subitem_uri = object_id_to_uri[subitem_id]
                    
                    # Add sub-item relationship
                    g.add((item_uri, FIREBIM.hasSubItem, subitem_uri))
                    g.add((subitem_uri, FIREBIM.isSubItemOf, item_uri))
                    
                    # Add subclass relationship - sub-item is a subclass of item
                    g.add((subitem_uri, RDFS.subClassOf, item_uri))
    
    # Save the ontology to a file
    g.serialize(destination="firebim_ontology_notion.ttl", format="turtle")
    print("Ontology saved to firebim_ontology_notion.ttl")

if __name__ == "__main__":
    create_ontology()