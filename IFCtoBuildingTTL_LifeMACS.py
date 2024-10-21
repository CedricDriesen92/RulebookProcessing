import ifcopenshell
import ifcopenshell.util.element
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD
import os
import psycopg2
from typing import Dict, List, Tuple

# Define namespaces
FBB = Namespace("http://example.org/firebimbuilding#")
BOT = Namespace("https://w3id.org/bot#")
BPO = Namespace("https://w3id.org/bpo#")
OPM = Namespace("https://w3id.org/opm#")
IFC = Namespace("http://example.org/IFC#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")
DOT = Namespace("http://example.org/dot#")

# IFC to BOT mapping
IFC_BOT_MAPPING = {
    "IfcBuilding": BOT.Building,
    "IfcBuildingStorey": BOT.Storey,
    "IfcBeam": BOT.Element,
    "IfcColumn": BOT.Element,
    "IfcSlab": BOT.Element,
    "IfcWall": BOT.Element,
    "IfcSite": BOT.Site,
}

# IFC to SOSA mapping
IFC_SOSA_MAPPING = {
    "IfcSensor": SOSA.Sensor,
}

# IFC to DOT mapping
IFC_DOT_MAPPING = {
    "IfcBuildingElementProxy": DOT.Damage,
}

# Property mappings
SENSOR_PROPERTIES = {
    "SensorID": SOSA.hasId,
    "SensorValueT": SOSA.hasSimpleResult
}

DAMAGE_PROPERTIES = {
    "Crack_ID": DOT.hasID,
    "Crack Width": DOT.hasWidth,
    "Crack Length": DOT.hasLength,
    "Crack Depth": DOT.hasDepth
}

GENERAL_PROPERTIES = {
    "Length": FBB.hasLength,
    "Width": FBB.hasWidth,
    "Height": FBB.hasHeight,
    "LoadBearing": FBB.isLoadBearing,
    "Material": FBB.hasMaterial,
    "Volume": FBB.hasVolume,
    "Area": FBB.hasArea,
    "Depth": FBB.hasDepth,
    "Thickness": FBB.hasThickness,
    "Span": FBB.hasSpan,
    "Slope": FBB.hasSlope,
    "Capacity": FBB.hasCapacity
}

class IFCtoMultiOntologyConverter:
    def __init__(self, ifc_file_path: str, output_ttl_path: str):
        self.ifc_file = ifcopenshell.open(ifc_file_path)
        print(self.ifc_file.schema)
        self.output_ttl_path = output_ttl_path
        self.g = Graph()
        self._bind_namespaces()
        self.db_connection = self._connect_to_database()
        print(self.db_connection)
        self.host_crack_mapping = self._get_host_crack_mapping()
        self.host_sensor_mapping = self._get_host_sensor_mapping()

    def _bind_namespaces(self) -> None:
        for prefix, namespace in [("fbb", FBB), ("bot", BOT), ("bpo", BPO), ("opm", OPM), ("ifc", IFC),
                                  ("sosa", SOSA), ("dot", DOT)]:
            self.g.bind(prefix, namespace)

    def create_uri(self, ns: Namespace, ifc_type: str, identifier: str) -> URIRef:
        return ns[f"{ifc_type}_{identifier}"]

    def process_ifc(self) -> None:
        print("Processing IFC file...")
        self._process_elements()

    def _process_elements(self) -> None:
        for ifc_type, bot_class in IFC_BOT_MAPPING.items():
            elements = self.ifc_file.by_type(ifc_type)
            for element in elements:
                self._process_single_element(element, ifc_type, bot_class)
        
        self._process_sensors()
        self._process_damage()

    def _process_single_element(self, element, ifc_type: str, bot_class) -> None:
        element_uri = self.create_uri(BOT, ifc_type, element.GlobalId)
        self.g.add((element_uri, RDF.type, bot_class))
        numeric_id = self._get_numeric_id(element)
        self.g.add((element_uri, FBB.hasID, Literal(numeric_id)))
        
        # Add general properties
        for prop_name, prop_predicate in GENERAL_PROPERTIES.items():
            prop_value = self._get_property(element, prop_name)
            if prop_value is not None:
                self.g.add((element_uri, prop_predicate, Literal(prop_value)))
        
        # Add material if available
        material = ifcopenshell.util.element.get_material(element)
        try:    
            if material and material.Name:
                self.g.add((element_uri, FBB.hasMaterial, Literal(material.Name)))
        except:
            pass

    def _process_sensors(self) -> None:
        sensors = self.ifc_file.by_type("IfcSensor")
        for sensor in sensors:
            sensor_uri = self.create_uri(SOSA, "Sensor", sensor.GlobalId)
            self.g.add((sensor_uri, RDF.type, SOSA.Sensor))
            self.g.add((sensor_uri, FBB.hasID, Literal(self._get_numeric_id(sensor))))
            
            for prop_name, prop_predicate in SENSOR_PROPERTIES.items():
                prop_value = self._get_property(sensor, prop_name)
                if prop_value is not None:
                    self.g.add((sensor_uri, prop_predicate, Literal(prop_value)))
                    
            for prop_name, prop_predicate in GENERAL_PROPERTIES.items():
                if prop_name not in SENSOR_PROPERTIES:
                    prop_value = self._get_property(sensor, prop_name)
                    if prop_value is not None:
                        self.g.add((sensor_uri, prop_predicate, Literal(prop_value)))

            # Add host relationship for sensors
            for host_id, sensor_ids in self.host_sensor_mapping.items():
                if any(self.g.value(sensor_uri, SOSA.hasId) == Literal(sensor_id) for sensor_id in sensor_ids):
                    #print(self.g.value(sensor_uri, SOSA.hasId)+" - "+host_id)
                    host_uri = self._find_element_uri_by_id(host_id)
                    if host_uri:
                        self.g.add((sensor_uri, FBB.hasHost, host_uri))
                        self.g.add((host_uri, FBB.hasSensor, sensor_uri))
                    else:
                        print(f"Warning: No element found with ID {host_id}")

    def _process_damage(self) -> None:
        damage_elements = self.ifc_file.by_type("IfcBuildingElementProxy")
        for damage in damage_elements:            
            props_found = False
            for prop_name, prop_predicate in DAMAGE_PROPERTIES.items():
                prop_value = self._get_property(damage, prop_name)
                if prop_value is not None:
                    props_found = True
            if props_found:
                damage_uri = self.create_uri(DOT, "Damage", damage.GlobalId)
                self.g.add((damage_uri, RDF.type, DOT.Damage))
                self.g.add((damage_uri, FBB.hasID, Literal(self._get_numeric_id(damage))))
            else:
                continue
            
            for prop_name, prop_predicate in DAMAGE_PROPERTIES.items():
                prop_value = self._get_property(damage, prop_name)
                if prop_value is not None:
                    self.g.add((damage_uri, prop_predicate, Literal(prop_value)))
                    
            for prop_name, prop_predicate in GENERAL_PROPERTIES.items():
                if prop_name not in DAMAGE_PROPERTIES:
                    prop_value = self._get_property(damage, prop_name)
                    if prop_value is not None:
                        self.g.add((damage_uri, prop_predicate, Literal(prop_value)))

            # Add host relationship for cracks
            for host_id, crack_ids in self.host_crack_mapping.items():
                if any(self.g.value(damage_uri, DOT.hasID) == Literal(crack_id) for crack_id in crack_ids):
                    #print(self.g.value(damage_uri, DOT.hasID)+" - "+host_id)
                    host_uri = self._find_element_uri_by_id(host_id)
                    if host_uri:
                        self.g.add((damage_uri, FBB.hasHost, host_uri))
                        self.g.add((host_uri, FBB.hasDamage, damage_uri))
                    else:
                        print(f"Warning: No element found with ID {host_id}")

    def _find_element_uri_by_id(self, element_id: str) -> URIRef:
        for s, p, o in self.g.triples((None, FBB.hasID, Literal(element_id))):
            return s
        return None

    def _get_property(self, element, property_name: str):
        psets = ifcopenshell.util.element.get_psets(element)
        for pset in psets.values():
            if property_name in pset:
                return pset[property_name]
        return None

    def _get_quantity(self, element, quantity_name: str):
        qtos = ifcopenshell.util.element.get_psets(element, qtos_only=True)
        for qto in qtos.values():
            if quantity_name in qto:
                return qto[quantity_name]
        return None

    def save_ttl(self) -> None:
        self.g.serialize(destination=self.output_ttl_path, format="turtle")
        self.db_connection.close()

    def _connect_to_database(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(
            host='buildwise.digital',
            user='postgresCedric',
            password='postgresCedric',
            database='postgres',
            port='5438'
        )

    def _get_host_crack_mapping(self) -> Dict[str, List[str]]:
        cursor = self.db_connection.cursor()
        cursor.execute("SELECT Host_ID, Crack_ID FROM Cracks")
        mapping = {}
        for host_id, crack_id in cursor.fetchall():
            if host_id not in mapping:
                mapping[host_id] = []
            mapping[host_id].append(crack_id)
        cursor.close()
        print(mapping)
        return mapping

    def _get_host_sensor_mapping(self) -> Dict[str, List[str]]:
        cursor = self.db_connection.cursor()
        cursor.execute("SELECT Host_ID, Sensor_ID FROM Sensors")
        mapping = {}
        for host_id, sensor_id in cursor.fetchall():
            if host_id not in mapping:
                mapping[host_id] = []
            mapping[host_id].append(sensor_id)
        cursor.close()
        print(mapping)
        return mapping

    def _get_numeric_id(self, element) -> str:
        # Try to get the 'Name' attribute, which often contains the desired ID
        name = getattr(element, 'Name', None)
        if name:
            # Split the name and get the last part, which is often the ID
            parts = name.split(':')
            if len(parts) > 1:
                return parts[-1]
        
        # If 'Name' is not available or doesn't contain the ID, fall back to the GlobalId
        return element.GlobalId

def ifc_to_multi_ontology_ttl(ifc_file_path: str, output_ttl_path: str) -> None:
    converter = IFCtoMultiOntologyConverter(ifc_file_path, output_ttl_path)
    converter.process_ifc()
    converter.save_ttl()

def main() -> None:
    main_dir = "IFCtoTTLin-outputs/"
    
    for file in os.listdir(main_dir):
        if file.lower().endswith("vc.ifc"):
            ifc_file_path = os.path.join(main_dir, file)
            ttl_file_path = os.path.join(main_dir, f"{os.path.splitext(file)[0]}_multi_ontology.ttl")
            
            ifc_to_multi_ontology_ttl(ifc_file_path, ttl_file_path)
            
            print(f"Converted {file} to {os.path.basename(ttl_file_path)}")
            print("\n")

if __name__ == "__main__":
    main()
