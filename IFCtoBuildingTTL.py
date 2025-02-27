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
FBB = Namespace("http://example.org/ontology/fbb#")
BOT = Namespace("https://w3id.org/bot#")
BPO = Namespace("https://w3id.org/bpo#")
OPM = Namespace("https://w3id.org/opm#")
IFC = Namespace("http://example.org/IFC#")
INST = Namespace("http://example.org/project#")

# IFC to BOT mapping
IFC_BOT_MAPPING = {
    "IfcBuilding": BOT.Building,
    "IfcBuildingStorey": BOT.Storey,
    "IfcSpace": BOT.Space,
    "IfcWall": BOT.Element,
    "IfcDoor": BOT.Element,
    "IfcWindow": BOT.Element,
    "IfcSlab": BOT.Element,
    "IfcBeam": BOT.Element,
    "IfcColumn": BOT.Element,
    "IfcStair": BOT.Element,
    "IfcRoof": BOT.Element,
    "IfcCovering": BOT.Element,
}

GENERAL_PROPERTIES = [
    "Width",
    "Height",
    "Depth",
    "Area",
    "Volume",
    "Compartment"
]

FIRE_SAFETY_PROPERTIES = [
    "FireRating",
    "FireResistanceRating",
    "FireCompartment",
    "SmokeCompartment",
    "IsExternal",
    "LoadBearing",
    "SprinklerProtection",
    "FireExit",
    "EvacuationRoute",
    "FireDetection",
    "FireSuppressionSystem",
    "FlammabilityRating",
    "SmokeDetection",
    "EmergencyLighting",
    "Fire",
    "HasCompartment",
    "HasSpace",
    "Compartment"
]

class IFCtoFBBConverter:
    def __init__(self, ifc_file_path: str, output_ttl_path: str, use_subclasses: bool = False):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.output_ttl_path = output_ttl_path
        self.g = Graph()
        self.use_subclasses = use_subclasses
        self._bind_namespaces()
        self.compartments = set()  # Track unique compartment names

    def sanitize_name(self, name: str):
        #name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        if name:
            return re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return "None"
    
    def _bind_namespaces(self) -> None:
        for prefix, namespace in [("fbb", FBB), ("bot", BOT), ("bpo", BPO), ("opm", OPM), ("ifc", IFC), ("inst", INST)]:
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
        building = self.ifc_file.by_type("IfcBuilding")[0]
        building_uri = self.create_uri(INST, "IfcBuilding", building.GlobalId)
        self.g.add((building_uri, RDF.type, IFC_BOT_MAPPING["IfcBuilding"]))
        self.g.add((building_uri, FBB.name, Literal(self.sanitize_name(building.Name))))
        self.add_properties(building, building_uri)

    def process_storeys(self) -> None:
        building = self.ifc_file.by_type("IfcBuilding")[0]
        building_uri = self.create_uri(INST, "IfcBuilding", building.GlobalId)
        storeys = self.ifc_file.by_type("IfcBuildingStorey")
        for i, storey in enumerate(storeys, 1):
            print(f"Processing storey {i} out of {len(storeys)}...")
            storey_uri = self.create_uri(INST, "IfcBuildingStorey", storey.GlobalId)
            self.g.add((storey_uri, RDF.type, IFC_BOT_MAPPING["IfcBuildingStorey"]))
            self.g.add((storey_uri, FBB.name, Literal(self.sanitize_name(storey.Name))))
            self.g.add((building_uri, BOT.hasStorey, storey_uri))
            self.add_properties(storey, storey_uri)

    def process_spaces(self) -> None:
        spaces = self.ifc_file.by_type("IfcSpace")
        for i, space in enumerate(spaces, 1):
            print(f"Processing space {i} out of {len(spaces)}...")
            space_uri = self.create_uri(INST, "IfcSpace", space.GlobalId)
            self.g.add((space_uri, RDF.type, IFC_BOT_MAPPING["IfcSpace"]))
            self.g.add((space_uri, FBB.name, Literal(self.sanitize_name(space.Name))))
            if space.Decomposes:
                storey = space.Decomposes[0].RelatingObject
                if storey.is_a("IfcBuildingStorey"):
                    storey_uri = self.create_uri(INST, "IfcBuildingStorey", storey.GlobalId)
                    self.g.add((storey_uri, BOT.hasSpace, space_uri))
            self.add_properties(space, space_uri)

    def process_elements(self) -> None:
        for h, element_type in enumerate(IFC_BOT_MAPPING, 1):
            print(f"Processing element type {h} out of {len(IFC_BOT_MAPPING)}...")
            if element_type not in ["IfcBuilding", "IfcBuildingStorey", "IfcSpace"]:
                elements = self.ifc_file.by_type(element_type)
                for element in elements:
                    self._process_single_element(element, element_type)

    def _process_single_element(self, element, element_type: str) -> None:
        element_uri = self.create_uri(INST, element_type, element.GlobalId)
        
        if self.use_subclasses:
            element_class_uri = self.create_uri(INST, element_type, "Class")
            self.g.add((element_class_uri, RDF.type, OWL.Class))
            self.g.add((element_class_uri, RDFS.subClassOf, BOT.Element))
            self.g.add((element_uri, RDF.type, element_class_uri))
        else:
            self.g.add((element_uri, RDF.type, IFC_BOT_MAPPING[element_type]))
            self.g.add((element_uri, FBB.hasIfcType, Literal(element_type)))
        
        self.g.add((element_uri, FBB.name, Literal(element.Name)))
        
        if hasattr(element, "ContainedInStructure") and element.ContainedInStructure:
            containing_storey = element.ContainedInStructure[0].RelatingStructure
            if containing_storey.is_a("IfcBuildingStorey"):
                storey_uri = self.create_uri(INST, "IfcBuildingStorey", containing_storey.GlobalId)
                self.g.add((storey_uri, BOT.containsElement, element_uri))
        
        self.add_properties(element, element_uri)

    def add_properties(self, ifc_entity, entity_uri: URIRef) -> None:
        psets = ifcopenshell.util.element.get_psets(ifc_entity)
        for pset_name, properties in psets.items():
            for prop_name, prop_value in properties.items():
                if prop_value is not None:
                    self._add_single_property(entity_uri, pset_name, prop_name, prop_value)

    def _add_single_property(self, entity_uri: URIRef, pset_name: str, prop_name: str, prop_value) -> None:
        sanitized_pset_name = self.sanitize_name(pset_name)
        sanitized_prop_name = self.sanitize_name(prop_name)
        
        # Handle Compartment property specially
        if prop_name == "Compartment" and prop_value:
            compartment_name = str(prop_value)
            sanitized_compartment_name = self.sanitize_name(compartment_name)
            
            # Create compartment instance if it doesn't exist yet
            if compartment_name not in self.compartments:
                self.compartments.add(compartment_name)
                compartment_uri = INST[f"compartment_{sanitized_compartment_name}"]
                self.g.add((compartment_uri, RDF.type, FBB.Compartment))
                self.g.add((compartment_uri, BPO.name, Literal(compartment_name)))
            
            # Link the entity to the compartment
            compartment_uri = INST[f"compartment_{sanitized_compartment_name}"]
            self.g.add((entity_uri, BPO.hasCompartment, compartment_uri))
            return
            
        # Format numeric values to avoid scientific notation
        if isinstance(prop_value, (int, float)):
            prop_value_formatted = f"{prop_value:.10g}"
        else:
            prop_value_formatted = prop_value
        
        if self.is_property_of_type(prop_name, GENERAL_PROPERTIES):
            property_uri = self.create_uri(BPO, f"{sanitized_prop_name}", "")
            self.g.add((entity_uri, property_uri, Literal(prop_value_formatted)))
            self.g.add((property_uri, RDF.type, BPO.Attribute))
            self.g.add((property_uri, RDFS.label, Literal(prop_name)))
        
        if self.is_property_of_type(prop_name, FIRE_SAFETY_PROPERTIES):
            property_uri = self.create_uri(BPO, f"{sanitized_pset_name}_{sanitized_prop_name}", "")
            self.g.add((entity_uri, property_uri, Literal(prop_value_formatted)))
            self.g.add((property_uri, RDF.type, BPO.Attribute))
            self.g.add((property_uri, RDFS.label, Literal(prop_name)))
            self.g.add((property_uri, FBB.isFireSafetyProperty, Literal(True)))

    def save_ttl(self) -> None:
        self.g.serialize(destination=self.output_ttl_path, format="turtle")

def get_unit_scale(ifc_file_path: str) -> float:
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
    return 1.0  # Default to meters if no unit is found

def test_external_door_width(ttl_file_path: str, ifc_file_path: str) -> List[Tuple[URIRef, float, URIRef]]:
    g = Graph()
    g.parse(ttl_file_path, format="turtle")

    unit_scale = get_unit_scale(ifc_file_path)

    query = """
    PREFIX fbb: <http://example.org/firebimbuilding#>
    PREFIX bpo: <https://w3id.org/bpo#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT ?door ?width ?isExternal ?widthProp
    WHERE {
        ?door fbb:hasIfcType "IfcDoor" .
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

def ifc_to_fbb_ttl(ifc_file_path: str, output_ttl_path: str, use_subclasses: bool = False) -> None:
    converter = IFCtoFBBConverter(ifc_file_path, output_ttl_path, use_subclasses)
    converter.process_ifc()
    converter.save_ttl()

def main() -> None:
    main_dir = "IFCtoTTLin-outputs/"
    use_subclasses = False
    
    for file in os.listdir(main_dir):
        if file.lower().endswith("ure.ifc"):
            ifc_file_path = os.path.join(main_dir, file)
            ttl_file_path = os.path.join(main_dir, f"{os.path.splitext(file)[0]}.ttl")
            
            ifc_to_fbb_ttl(ifc_file_path, ttl_file_path, use_subclasses)
            
            print(f"Testing external door widths for {file}...")
            non_compliant_doors = []#test_external_door_width(ttl_file_path, ifc_file_path)
            
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