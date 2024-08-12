import ifcopenshell
import ifcopenshell.util.element
import rdflib
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD
import os
from fuzzywuzzy import fuzz
import re

# Define namespaces
FBB = Namespace("http://example.org/firebimbuilding#")
BOT = Namespace("https://w3id.org/bot#")
BPO = Namespace("https://w3id.org/bpo#")
OPM = Namespace("https://w3id.org/opm#")
IFC = Namespace("http://example.org/IFC#")

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
    "Area"
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
]

class IFCtoFBBConverter:
    def __init__(self, ifc_file_path, output_ttl_path, use_subclasses=False):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        self.output_ttl_path = output_ttl_path
        self.g = Graph()
        self.use_subclasses = use_subclasses

        # Bind namespaces to the graph
        self.g.bind("fbb", FBB)
        self.g.bind("bot", BOT)
        self.g.bind("bpo", BPO)
        self.g.bind("opm", OPM)
        self.g.bind("ifc", IFC)

    def create_uri(self, ns, name):
        sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        return ns[sanitized_name]

    def is_fire_safety_property(self, prop_name):
        return any((fuzz.ratio(prop_name.lower(), fs_prop.lower()) > 80 or fs_prop.lower() in prop_name.lower()) for fs_prop in FIRE_SAFETY_PROPERTIES)

    def is_general_property(self, prop_name):
        return any((fuzz.ratio(prop_name.lower(), fs_prop.lower()) > 80 or fs_prop.lower() in prop_name.lower()) for fs_prop in GENERAL_PROPERTIES)

    def process_ifc(self):
        print("Processing building...")
        self.process_building()
        self.process_storeys()
        self.process_spaces()
        self.process_elements()

    def process_building(self):
        building = self.ifc_file.by_type("IfcBuilding")[0]
        building_uri = self.create_uri(FBB, f"Building_{building.Name}_{building.GlobalId}")
        self.g.add((building_uri, RDF.type, IFC_BOT_MAPPING["IfcBuilding"]))
        self.add_properties(building, building_uri)

    def process_storeys(self):
        building_uri = self.create_uri(FBB, f"Building_{self.ifc_file.by_type('IfcBuilding')[0].Name}_{self.ifc_file.by_type('IfcBuilding')[0].GlobalId}")
        storeys = self.ifc_file.by_type("IfcBuildingStorey")
        for i, storey in enumerate(storeys):
            print(f"Processing storey {i+1} out of {len(storeys)}...")
            storey_uri = self.create_uri(FBB, f"Storey_{storey.Name}_{storey.GlobalId}")
            self.g.add((storey_uri, RDF.type, IFC_BOT_MAPPING["IfcBuildingStorey"]))
            self.g.add((building_uri, BOT.hasStorey, storey_uri))
            self.add_properties(storey, storey_uri)

    def process_spaces(self):
        spaces = self.ifc_file.by_type("IfcSpace")
        for i, space in enumerate(spaces):
            print(f"Processing space {i+1} out of {len(spaces)}...")
            space_uri = self.create_uri(FBB, f"Space_{space.Name}_{space.GlobalId}")
            self.g.add((space_uri, RDF.type, IFC_BOT_MAPPING["IfcSpace"]))
            if space.Decomposes:
                storey = space.Decomposes[0].RelatingObject
                if storey.is_a("IfcBuildingStorey"):
                    storey_uri = self.create_uri(FBB, f"Storey_{storey.Name}_{storey.GlobalId}")
                    self.g.add((storey_uri, BOT.hasSpace, space_uri))
            self.add_properties(space, space_uri)

    def process_elements(self):
        for h, element_type in enumerate(IFC_BOT_MAPPING):
            print(f"Processing element type {h+1} out of {len(IFC_BOT_MAPPING)}...")
            if element_type not in ["IfcBuilding", "IfcBuildingStorey", "IfcSpace"]:
                elements = self.ifc_file.by_type(element_type)
                for i, element in enumerate(elements):
                    element_uri = self.create_uri(FBB, f"Element_{element.Name}_{element.GlobalId}")
                    
                    if self.use_subclasses:
                        element_class_uri = self.create_uri(FBB, element_type)
                        self.g.add((element_class_uri, RDF.type, OWL.Class))
                        self.g.add((element_class_uri, RDFS.subClassOf, BOT.Element))
                        self.g.add((element_uri, RDF.type, element_class_uri))
                    else:
                        self.g.add((element_uri, RDF.type, IFC_BOT_MAPPING[element_type]))
                        self.g.add((element_uri, FBB.hasIfcType, Literal(element_type)))
                    
                    if hasattr(element, "ContainedInStructure") and element.ContainedInStructure:
                        containing_storey = element.ContainedInStructure[0].RelatingStructure
                        if containing_storey.is_a("IfcBuildingStorey"):
                            storey_uri = self.create_uri(FBB, f"Storey_{containing_storey.Name}_{containing_storey.GlobalId}")
                            self.g.add((storey_uri, BOT.containsElement, element_uri))
                    
                    self.add_properties(element, element_uri)

    def add_properties(self, ifc_entity, entity_uri):
        psets = ifcopenshell.util.element.get_psets(ifc_entity)
        for pset_name, properties in psets.items():
            for prop_name, prop_value in properties.items():
                if prop_value is not None:
                    sanitized_prop_name = re.sub(r'[^a-zA-Z0-9_]', '_', prop_name)
                    if self.is_general_property(prop_name):
                        property_uri = self.create_uri(BPO, f"{pset_name}_{sanitized_prop_name}")
                        self.g.add((entity_uri, property_uri, Literal(prop_value)))
                        self.g.add((property_uri, RDF.type, BPO.Attribute))
                        self.g.add((property_uri, RDFS.label, Literal(prop_name)))
                    
                    elif self.is_fire_safety_property(prop_name):
                        property_uri = self.create_uri(BPO, f"{pset_name}_{sanitized_prop_name}")
                        self.g.add((entity_uri, property_uri, Literal(prop_value)))
                        self.g.add((property_uri, RDF.type, BPO.Attribute))
                        self.g.add((property_uri, RDFS.label, Literal(prop_name)))
                        self.g.add((property_uri, FBB.isFireSafetyProperty, Literal(True)))

    def save_ttl(self):
        self.g.serialize(destination=self.output_ttl_path, format="turtle")

def ifc_to_fbb_ttl(ifc_file_path, output_ttl_path, use_subclasses=False):
    converter = IFCtoFBBConverter(ifc_file_path, output_ttl_path, use_subclasses)
    converter.process_ifc()
    converter.save_ttl()


def get_unit_scale(ifc_file_path):
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

def test_external_door_width(ttl_file_path, ifc_file_path):
    g = Graph()
    g.parse(ttl_file_path, format="turtle")

    unit_scale = get_unit_scale(ifc_file_path)

    FBB = Namespace("http://example.org/firebimbuilding#")
    BPO = Namespace("https://w3id.org/bpo#")

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
            print(f"Error: {e}")

    return non_compliant_doors




if __name__ == "__main__":
    main_dir = "IFCtoTTLin-outputs/"
    use_subclasses = False
    
    for file in os.listdir(main_dir):
        if file.lower().endswith(".ifc"):
            ifc_file_path = os.path.join(main_dir, file)
            ttl_file_path = os.path.join(main_dir, file.rsplit(".", 1)[0] + ".ttl")
            
            ifc_to_fbb_ttl(ifc_file_path, ttl_file_path, use_subclasses)
            
            print(f"Testing external door widths for {file}...")
            non_compliant_doors = test_external_door_width(ttl_file_path, ifc_file_path)
            
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