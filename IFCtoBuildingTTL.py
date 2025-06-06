import ifcopenshell
import ifcopenshell.util.element
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD
import os
from fuzzywuzzy import fuzz
import re
from typing import List, Tuple, Dict
import unicodedata

# Define namespaces
FBO = Namespace("https://ontology.firebim.be/ontology/fbo#")  # General FireBIM Building Ontology
FBO_BE = Namespace("https://ontology.firebim.be/ontology/fbo-BE#")
FBO_NL = Namespace("https://ontology.firebim.be/ontology/fbo-NL#")
FBO_DK = Namespace("https://ontology.firebim.be/ontology/fbo-DK#")
FBO_PT = Namespace("https://ontology.firebim.be/ontology/fbo-PT#")
FBO_INT = Namespace("https://ontology.firebim.be/ontology/fbo-INT#")  # International

BOT = Namespace("https://w3id.org/bot#")
BPO = Namespace("https://w3id.org/bpo#")
OPM = Namespace("https://w3id.org/opm#")
IFC = Namespace("http://example.org/IFC#")
INST = Namespace("http://example.org/project#")
FRO = Namespace("https://ontology.firebim.be/ontology/fro#")

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

# Load the FireBIM ontology
def load_firebim_ontology(ontology_path="buildingontologies/firebim_ontology_alex.ttl", preferred_country="BE"):
    print(f"Loading FireBIM ontology from {ontology_path}...")
    g = Graph()
    try:
        g.parse(ontology_path, format="turtle")
        print(f"Successfully loaded ontology with {len(g)} triples")
        return g, preferred_country
    except Exception as e:
        print(f"Error loading ontology: {e}")
        print("Using default mappings instead")
        return None, preferred_country
 
def build_ifc_bot_mapping(ontology_graph, preferred_country="BE"):
    """Build IFC to FireBIM ontology mapping from the FireBIM ontology"""
    mapping = {}
    
    if ontology_graph is None:
        # Return default mappings if ontology couldn't be loaded
        country_ns = get_country_namespace(preferred_country)
        return {
            "IfcBuilding": country_ns.Building,
            "IfcBuildingStorey": country_ns.Storey,
            "IfcSpace": country_ns.Space,
            "IfcWall": country_ns.Wall,
            "IfcDoor": country_ns.Door,
            "IfcWindow": country_ns.Window,
            "IfcSlab": country_ns.Slab,
            "IfcBeam": country_ns.Beam,
            "IfcColumn": country_ns.Column,
            "IfcStair": country_ns.Stair,
            "IfcRoof": country_ns.Roof,
            "IfcCovering": country_ns.Covering,
        }
    
    # Get the preferred country namespace
    preferred_ns = get_country_namespace(preferred_country)
    
    # Query for objects that have an IFC entity mapping
    # First try to find country-specific classes
    query = f"""
    PREFIX fbo: <https://ontology.firebim.be/ontology/fbo#>
    PREFIX fbo-{preferred_country}: <https://ontology.firebim.be/ontology/fbo-{preferred_country}#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    
    SELECT ?firebimClass ?ifcEntity
    WHERE {{
        ?firebimClass fbo:hasIFCEntity ?ifcEntity .
        ?firebimClass rdfs:subClassOf ?generalClass .
        FILTER(STRSTARTS(STR(?firebimClass), STR(fbo-{preferred_country}:)))
    }}
    """
    
    results = ontology_graph.query(query)
    
    # If no country-specific classes found, try general classes
    if not results:
        query = """
        PREFIX fbo: <https://ontology.firebim.be/ontology/fbo#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        
        SELECT ?firebimClass ?ifcEntity
        WHERE {
            ?firebimClass fbo:hasIFCEntity ?ifcEntity .
        }
        """
        results = ontology_graph.query(query)
    
    for row in results:
        ifc_entity = str(row['ifcEntity'])
        firebim_class = row['firebimClass']
        
        # Handle multiple IFC entities (comma-separated)
        ifc_entities = [e.strip() for e in ifc_entity.split(',')]
        for entity in ifc_entities:
            # Extract the base class (before any dot)
            ifc_class = entity.split('.')[0] if '.' in entity else entity
            mapping[ifc_class] = firebim_class
    
    # Add default mappings for common IFC entities if not already in the mapping
    default_mappings = {
        "IfcBuilding": preferred_ns.Building,
        "IfcBuildingStorey": preferred_ns.Storey,
        "IfcSpace": preferred_ns.Space,
        "IfcWall": preferred_ns.Wall,
        "IfcDoor": preferred_ns.Door,
        "IfcWindow": preferred_ns.Window,
        "IfcSlab": preferred_ns.Slab,
        "IfcBeam": preferred_ns.Beam,
        "IfcColumn": preferred_ns.Column,
        "IfcStair": preferred_ns.Stair,
        "IfcRoof": preferred_ns.Roof,
        "IfcCovering": preferred_ns.Covering,
    }
    
    for ifc_class, firebim_class in default_mappings.items():
        if ifc_class not in mapping:
            mapping[ifc_class] = firebim_class
    
    print(f"Built IFC to FireBIM mapping with {len(mapping)} entries for country {preferred_country}")
    return mapping

def extract_properties_from_ontology(ontology_graph, preferred_country="BE"):
    """Extract general and fire safety properties from the FireBIM ontology"""
    general_properties = []
    fire_safety_properties = []
    
    if ontology_graph is None:
        # Return default property lists if ontology couldn't be loaded
        return (
            ["Width", "Height", "Depth", "Area", "Volume", "Compartment"],
            [
                "FireRating", "FireResistanceRating", "FireCompartment", 
                "SmokeCompartment", "IsExternal", "LoadBearing", 
                "SprinklerProtection", "FireExit", "EvacuationRoute", 
                "FireDetection", "FireSuppressionSystem", "FlammabilityRating", 
                "SmokeDetection", "EmergencyLighting", "Fire", 
                "HasCompartment", "HasSpace", "Compartment"
            ]
        )
    
    # Query for properties and their English labels, prioritizing country-specific properties
    query = f"""
    PREFIX fbo: <https://ontology.firebim.be/ontology/fbo#>
    PREFIX fbo-{preferred_country}: <https://ontology.firebim.be/ontology/fbo-{preferred_country}#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    
    SELECT ?property ?label ?domain ?isFireSafety
    WHERE {{
        ?property rdf:type owl:ObjectProperty .
        ?property rdfs:label ?label .
        FILTER(LANG(?label) = "en" || LANG(?label) = "")
        
        OPTIONAL {{ ?property fbo:hasDomain ?domain }}
        OPTIONAL {{ 
            ?property fbo:isFireSafetyProperty ?isFireSafety 
            FILTER(?isFireSafety = true)
        }}
        
        # Prioritize country-specific properties
        OPTIONAL {{ 
            ?property rdfs:subPropertyOf ?generalProperty .
            FILTER(STRSTARTS(STR(?property), STR(fbo-{preferred_country}:)))
        }}
    }}
    ORDER BY DESC(BOUND(?generalProperty))
    """
    
    results = ontology_graph.query(query)
    
    for row in results:
        property_label = str(row['label'])
        domain = row['domain'] if row['domain'] else None
        is_fire_safety = bool(row['isFireSafety']) if row['isFireSafety'] else False
        
        # Add to appropriate list based on domain or fire safety flag
        if is_fire_safety:
            fire_safety_properties.append(property_label)
        elif domain and "fire" in str(domain).lower():
            fire_safety_properties.append(property_label)
        else:
            general_properties.append(property_label)
    
    # Add default properties if lists are empty
    if not general_properties:
        general_properties = ["Width", "Height", "Depth", "Area", "Volume", "Compartment"]
    else:
        general_properties = general_properties + ["Width", "Height", "Depth", "Area", "Volume", "Compartment"]
    
    if not fire_safety_properties:
        fire_safety_properties = [
            "FireRating", "FireResistanceRating", "FireCompartment", 
            "SmokeCompartment", "IsExternal", "LoadBearing", 
            "SprinklerProtection", "FireExit", "EvacuationRoute", 
            "FireDetection", "FireSuppressionSystem", "FlammabilityRating", 
            "SmokeDetection", "EmergencyLighting", "Fire", 
            "HasCompartment", "HasSpace", "Compartment"
        ]
    else:
        fire_safety_properties = fire_safety_properties + [
            "FireRating", "FireResistanceRating", "FireCompartment", 
            "SmokeCompartment", "IsExternal", "LoadBearing", 
            "SprinklerProtection", "FireExit", "EvacuationRoute", 
            "FireDetection", "FireSuppressionSystem", "FlammabilityRating", 
            "SmokeDetection", "EmergencyLighting", "Fire", 
            "HasCompartment", "HasSpace", "Compartment"
        ]
    
    # Ensure "Compartment" is in general properties for backward compatibility
    if "Compartment" not in general_properties:
        general_properties.append("Compartment")
    
    print(f"Extracted {len(general_properties)} general properties and {len(fire_safety_properties)} fire safety properties")
    return general_properties, fire_safety_properties

# Load the ontology and build the mapping with preferred country
PREFERRED_COUNTRY = "INT"  # Default to Belgium
ONTOLOGY_GRAPH, PREFERRED_COUNTRY = load_firebim_ontology(preferred_country=PREFERRED_COUNTRY)
IFC_BOT_MAPPING = build_ifc_bot_mapping(ONTOLOGY_GRAPH, preferred_country=PREFERRED_COUNTRY)
GENERAL_PROPERTIES, FIRE_SAFETY_PROPERTIES = extract_properties_from_ontology(ONTOLOGY_GRAPH, preferred_country=PREFERRED_COUNTRY)

class IFCtofboConverter:
    def __init__(self, ifc_file_path: str, output_ttl_path: str, use_subclasses: bool = False, preferred_country: str = "BE"):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.output_ttl_path = output_ttl_path
        self.g = Graph()
        self.use_subclasses = use_subclasses
        self.preferred_country = preferred_country
        self._bind_namespaces()
        self.compartments = set()  # Track unique compartment names

        # Map common property names (lowercase) to FBO predicates
        self.PROPERTY_NAME_TO_FBO_PREDICATE = {
            "area": FBO.hasArea,
            "length": FBO.hasLength,
            "width": FBO.hasWidth, # Example, add as needed
            "height": FBO.hasHeight, # Example, add as needed
            "firerating": FBO.hasFireRating, # Check actual FBO property URI
            "isexternal": FBO.isExternal,     # Check actual FBO property URI
            "loadbearing": FBO.isLoadBearing, # Check actual FBO property URI
            # Properties from SHACL shape for fbo:Compartment
            "automaticextinguishingsystem": FBO.hasAutomaticExtinguishingSystem,
            "smokeandheatevacuationsystem": FBO.hasSmokeAndHeatEvacuationSystem,
            # Properties from SHACL for fbo:Building (if found on IfcBuilding entities)
            "isgroundflooronly": FBO.isGroundFloorOnly,
            "numberofcompartments": FBO.hasNumberOfCompartments,
        }

        # FBO Predicates that should be attached to the compartment URI
        # if the IFC entity defines a compartment and has these properties.
        self.COMPARTMENT_SPECIFIC_FBO_PREDICATES = {
            FBO.hasLength,
            FBO.hasFireRating, # Example
            FBO.hasAutomaticExtinguishingSystem,
            FBO.hasSmokeAndHeatEvacuationSystem,
            # Note: FBO.hasArea is intentionally NOT here, as it's typically on spaces
            # for the SHACL rule to infer compartment area.
        }

    def sanitize_name(self, name: str):
        #name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        if name:
            return re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return "None"
    
    def _bind_namespaces(self) -> None:
        # Bind all namespaces including country-specific ones
        for prefix, namespace in [
            ("fbo", FBO), 
            ("fbo-BE", FBO_BE),
            ("fbo-NL", FBO_NL),
            ("fbo-DK", FBO_DK),
            ("fbo-PT", FBO_PT),
            ("fbo-INT", FBO_INT),
            ("bot", BOT), 
            ("bpo", BPO), 
            ("opm", OPM), 
            ("ifc", IFC), 
            ("inst", INST)
        ]:
            self.g.bind(prefix, namespace)

    def create_uri(self, ns: Namespace, ifc_type: str, global_id: str) -> URIRef:
        entity_name = ifc_type[3:] if ifc_type.startswith("Ifc") else ifc_type
        if len(global_id) > 0:
            return ns[f"{self.sanitize_name(entity_name)}_{self.sanitize_name(global_id)}"]
        else:
            return ns[self.sanitize_name(entity_name)]

    @staticmethod
    def is_property_of_type(prop_name: str, property_list: List[str], threshold: int = 80) -> bool:
        return any((fuzz.ratio(prop_name.lower(), prop.lower()) > threshold or 
                    prop.lower() in prop_name.lower()) for prop in property_list)

    def process_ifc(self) -> None:
        print("Processing IFC file...")
        self.process_building()
        self.process_storeys()
        self.process_spaces()
        self.process_elements()

    def process_building(self) -> None:
        buildings = self.ifc_file.by_type("IfcBuilding")
        if not buildings:
            print("Warning: No IfcBuilding found in the IFC file")
            return
            
        building = buildings[0]
        global_id = getattr(building, "GlobalId", f"Building_{building.id()}")
        building_uri = self.create_uri(INST, "IfcBuilding", global_id)
        self.g.add((building_uri, RDF.type, IFC_BOT_MAPPING["IfcBuilding"]))
        
        name = getattr(building, "Name", f"Building_{building.id()}")
        self.g.add((building_uri, RDFS.label, Literal(self.sanitize_name(name))))
        
        self.add_properties(building, building_uri)

    def process_storeys(self) -> None:
        buildings = self.ifc_file.by_type("IfcBuilding")
        if not buildings:
            print("Warning: No IfcBuilding found in the IFC file")
            return
            
        building = buildings[0]
        global_id = getattr(building, "GlobalId", f"Building_{building.id()}")
        building_uri = self.create_uri(INST, "IfcBuilding", global_id)
        
        storeys = self.ifc_file.by_type("IfcBuildingStorey")
        for i, storey in enumerate(storeys, 1):
            print(f"Processing storey {i} out of {len(storeys)}...")
            storey_global_id = getattr(storey, "GlobalId", f"Storey_{storey.id()}")
            storey_uri = self.create_uri(INST, "IfcBuildingStorey", storey_global_id)
            self.g.add((storey_uri, RDF.type, IFC_BOT_MAPPING["IfcBuildingStorey"]))
            
            storey_name = getattr(storey, "Name", f"Storey_{storey.id()}")
            self.g.add((storey_uri, RDFS.label, Literal(self.sanitize_name(storey_name))))
            
            self.g.add((building_uri, FRO.hasStorey, storey_uri))
            self.add_properties(storey, storey_uri)

    def process_spaces(self) -> None:
        spaces = self.ifc_file.by_type("IfcSpace")
        for i, space in enumerate(spaces, 1):
            print(f"Processing space {i} out of {len(spaces)}...")
            space_global_id = getattr(space, "GlobalId", f"Space_{space.id()}")
            space_uri = self.create_uri(INST, "IfcSpace", space_global_id)
            self.g.add((space_uri, RDF.type, IFC_BOT_MAPPING["IfcSpace"]))
            
            space_name = getattr(space, "Name", f"Space_{space.id()}")
            self.g.add((space_uri, RDFS.label, Literal(self.sanitize_name(space_name))))
            
            if hasattr(space, "Decomposes") and space.Decomposes:
                storey = space.Decomposes[0].RelatingObject
                if storey.is_a("IfcBuildingStorey"):
                    storey_global_id = getattr(storey, "GlobalId", f"Storey_{storey.id()}")
                    storey_uri = self.create_uri(INST, "IfcBuildingStorey", storey_global_id)
                    self.g.add((storey_uri, FRO.hasSpace, space_uri))
            
            self.add_properties(space, space_uri)

    def process_elements(self) -> None:
        for h, element_type in enumerate(IFC_BOT_MAPPING, 1):
            print(f"Processing element type {h} out of {len(IFC_BOT_MAPPING)}...")
            if element_type not in ["IfcBuilding", "IfcBuildingStorey", "IfcSpace"]:
                try:
                    elements = self.ifc_file.by_type(element_type)
                    if not elements:
                        print(f"No {element_type} elements found in the IFC file")
                        continue
                        
                    for element in elements:
                        try:
                            self._process_single_element(element, element_type)
                        except Exception as e:
                            print(f"Error processing {element_type} (id: {element.id()}): {e}")
                except Exception as e:
                    print(f"Error processing element type {element_type}: {e}")

    def _process_single_element(self, element, element_type: str) -> None:
        # Check if element has GlobalId attribute, use a fallback if not
        global_id = getattr(element, "GlobalId", None)
        if global_id is None:
            # For entities without GlobalId, use a combination of type and id
            global_id = f"{element_type}_{element.id()}"
        
        element_uri = self.create_uri(INST, element_type, global_id)
        
        # Use the FireBIM ontology mapping instead of BOT
        self.g.add((element_uri, RDF.type, IFC_BOT_MAPPING[element_type]))
        
        # Check if element has Name attribute, use a fallback if not
        name = getattr(element, "Name", None)
        if name is None:
            # For entities without Name, use the type and id
            name = f"{element_type}_{element.id()}"
        
        self.g.add((element_uri, RDFS.label, Literal(self.sanitize_name(name))))
        
        # Check if element has ContainedInStructure attribute
        if hasattr(element, "ContainedInStructure") and element.ContainedInStructure:
            containing_storey = element.ContainedInStructure[0].RelatingStructure
            if containing_storey.is_a("IfcBuildingStorey"):
                storey_global_id = getattr(containing_storey, "GlobalId", f"Storey_{containing_storey.id()}")
                storey_uri = self.create_uri(INST, "IfcBuildingStorey", storey_global_id)
                self.g.add((storey_uri, FRO.containsElement, element_uri))
        
        self.add_properties(element, element_uri)

    def add_properties(self, ifc_entity, entity_uri: URIRef) -> None:
        try:
            psets = ifcopenshell.util.element.get_psets(ifc_entity)
            
            entitys_associated_compartment_uri = None
            # Check if this IFC entity has a "Compartment" property, to identify its associated compartment URI
            for pset_name_check, properties_check in psets.items():
                compartment_prop_val = None
                for key, val in properties_check.items():
                    if key.lower() == "compartment": # Case-insensitive check for "Compartment" property
                        compartment_prop_val = val
                        break
                
                if compartment_prop_val:
                    compartment_name_for_entity = str(compartment_prop_val)
                    if compartment_name_for_entity: # Ensure not empty
                        sanitized_compartment_name = self.sanitize_name(compartment_name_for_entity)
                        entitys_associated_compartment_uri = INST[f"compartment_{sanitized_compartment_name}"]
                        break # Found compartment association for this entity
            
            for pset_name, properties in psets.items():
                for prop_name, prop_value in properties.items():
                    if prop_value is not None:
                        self._add_single_property(entity_uri, pset_name, prop_name, prop_value,
                                                 entitys_compartment_uri=entitys_associated_compartment_uri)
        except Exception as e:
            print(f"Error getting properties for entity {ifc_entity.id()}: {e}")

    def _add_single_property(self, entity_uri: URIRef, pset_name: str, prop_name: str, prop_value,
                             entitys_compartment_uri: URIRef = None) -> None:
        
        # 1. Handle the "Compartment" property assignment itself.
        # This links entity_uri (e.g. a space) to an fbo:Compartment instance.
        if prop_name.lower() == "compartment" and prop_value:
            compartment_name = str(prop_value)
            if not compartment_name: # Skip if compartment name is empty
                return

            sanitized_compartment_name = self.sanitize_name(compartment_name)
            
            # This is the URI of the compartment instance being referenced or created.
            defined_compartment_uri = INST[f"compartment_{sanitized_compartment_name}"]
            
            if compartment_name not in self.compartments:
                self.compartments.add(compartment_name)
                self.g.add((defined_compartment_uri, RDF.type, FBO.Compartment))
                self.g.add((defined_compartment_uri, RDFS.label, Literal(compartment_name))) # Use RDFS.label for name
            
            # Link the current entity (entity_uri) to this compartment.
            self.g.add((entity_uri, FBO.hasCompartment, defined_compartment_uri))
            return # "Compartment" property fully processed.

        # 2. Format prop_value into an RDF Literal with appropriate XSD datatype.
        prop_value_literal: Literal
        if isinstance(prop_value, bool):
            prop_value_literal = Literal(prop_value, datatype=XSD.boolean)
        elif isinstance(prop_value, int):
            prop_value_literal = Literal(prop_value, datatype=XSD.integer)
        elif isinstance(prop_value, float):
            prop_value_literal = Literal(f"{prop_value:.10g}", datatype=XSD.double) # Avoid scientific notation
        else:
            prop_value_literal = Literal(str(prop_value))

        # 3. Process other properties: Check for specific FBO predicate mapping.
        # Use original prop_name for lookup in map keys, assuming map keys match IFC PSet names.
        # Using .lower() for robustness if PSet names vary in case.
        mapped_fbo_predicate = self.PROPERTY_NAME_TO_FBO_PREDICATE.get(prop_name.lower())

        if mapped_fbo_predicate:
            # A specific FBO predicate is found for this prop_name.
            # Determine the subject for this triple:
            # - If this entity defines/belongs to a compartment (entitys_compartment_uri is not None)
            #   AND the property is compartment-specific (e.g. FBO.hasLength),
            #   then the subject is the compartment's URI.
            # - Otherwise, the subject is the entity's URI itself (e.g. FBO.hasArea for a space).
            
            target_subject_uri = entity_uri # Default subject
            if entitys_compartment_uri and mapped_fbo_predicate in self.COMPARTMENT_SPECIFIC_FBO_PREDICATES:
                target_subject_uri = entitys_compartment_uri
            
            self.g.add((target_subject_uri, mapped_fbo_predicate, prop_value_literal))
        
        else:
            # 4. Fallback: No specific FBO mapping found. Use generic BPO property creation.
            # This logic remains similar to original, attaching properties to the entity_uri.
            sanitized_prop_name_for_bpo = self.sanitize_name(prop_name)
            if self.is_property_of_type(prop_name, GENERAL_PROPERTIES):
                property_uri = self.create_uri(BPO, f"{sanitized_prop_name_for_bpo}", "")
                self.g.add((entity_uri, property_uri, prop_value_literal))
                self.g.add((property_uri, RDF.type, BPO.Attribute))
                self.g.add((property_uri, RDFS.label, Literal(prop_name))) # Original prop_name for label
            
            if self.is_property_of_type(prop_name, FIRE_SAFETY_PROPERTIES):
                # For fire safety, original logic included pset_name in URI, which can be kept for differentiation.
                sanitized_pset_name = self.sanitize_name(pset_name)
                property_uri = self.create_uri(BPO, f"{sanitized_pset_name}_{sanitized_prop_name_for_bpo}", "")
                self.g.add((entity_uri, property_uri, prop_value_literal))
                self.g.add((property_uri, RDF.type, BPO.Attribute))
                self.g.add((property_uri, RDFS.label, Literal(prop_name)))
                self.g.add((property_uri, FBO.isFireSafetyProperty, Literal(True, datatype=XSD.boolean)))

    def save_ttl(self) -> None:
        self.g.serialize(destination=self.output_ttl_path, format="turtle")

def get_unit_scale(ifc_file_path: str) -> float:
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        project = ifc_file.by_type("IfcProject")[0]
        units = project.UnitsInContext.Units
        for unit in units:
            if unit.is_a("IfcSIUnit") and unit.UnitType == "LENGTHUNIT":
                if unit.Prefix == "MILLI":
                    return 0.001  # Millimeters to meters
                elif unit.Prefix == "CENTI":
                    return 0.01   # Centimeters to meters
                else:
                    return 1.0    # Already in meters
    except Exception as e:
        print(f"Error determining unit scale: {e}")
    return 1.0  # Default to meters if no unit is found

def test_external_door_width(ttl_file_path: str, ifc_file_path: str) -> List[Tuple[URIRef, float, URIRef]]:
    g = Graph()
    g.parse(ttl_file_path, format="turtle")

    unit_scale = get_unit_scale(ifc_file_path)

    query = """
    PREFIX fbo: <https://ontology.firebim.be/ontology/fbo#>
    PREFIX bpo: <https://w3id.org/bpo#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT ?door ?width ?isExternal ?widthProp
    WHERE {
        ?door fbo:hasIfcType "IfcDoor" .
        ?door ?isExternalProp ?isExternal .
        FILTER(CONTAINS(LCASE(STR(?isExternalProp)), "external"))
        ?door ?widthProp ?width .
        FILTER(CONTAINS(LCASE(STR(?widthProp)), "width"))
    }
    """

    results = g.query(query)
    non_compliant_doors = []

    for row in results:
        try:
            door = row['door']
            width = float(row['width']) * unit_scale
            is_external = row['isExternal']
            width_prop = row['widthProp']

            if str(is_external).lower() == 'true' and width <= 0.8:
                non_compliant_doors.append((door, width, width_prop))
        except Exception as e:
            print(f"Error processing door: {e}")

    return non_compliant_doors

def ifc_to_fbo_ttl(ifc_file_path: str, output_ttl_path: str, use_subclasses: bool = False, preferred_country: str = "BE") -> None:
    try:
        converter = IFCtofboConverter(ifc_file_path, output_ttl_path, use_subclasses, preferred_country)
        converter.process_ifc()
        converter.save_ttl()
        print(f"Successfully converted {ifc_file_path} to {output_ttl_path}")
    except Exception as e:
        print(f"Error converting {ifc_file_path}: {e}")

def main() -> None:
    main_dir = "IFCtoTTLin-outputs/"
    use_subclasses = True
    preferred_country = "BE"  # Default to Belgium
    
    # Ensure the output directory exists
    if not os.path.exists(main_dir):
        print(f"Creating output directory: {main_dir}")
        os.makedirs(main_dir)
    
    for file in os.listdir(main_dir):
        if file.lower().endswith("ure.ifc"):
            ifc_file_path = os.path.join(main_dir, file)
            ttl_file_path = os.path.join(main_dir, f"{os.path.splitext(file)[0]}.ttl")
            
            print(f"Processing IFC file: {file}")
            ifc_to_fbo_ttl(ifc_file_path, ttl_file_path, use_subclasses, preferred_country)
            
            print(f"Testing external door widths for {file}...")
            non_compliant_doors = []  # Uncomment to enable: test_external_door_width(ttl_file_path, ifc_file_path)
            
            if non_compliant_doors:
                print(f"Found {len(non_compliant_doors)} non-compliant external doors:")
                for door, width, width_prop in non_compliant_doors:
                    print(f"Door: {door}")
                    print(f"Width: {width:.2f} m")
                    print(f"Width Property: {width_prop}")
                    print()
            else:
                print("All external doors comply with the width requirement.")
            
            print("\n")

if __name__ == "__main__":
    main()