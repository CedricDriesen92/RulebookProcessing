import rdflib
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, SH
import re
from typing import Dict, List, Set, Tuple
import hashlib

class SHACLToMermaid:
    def __init__(self):
        self.seen_nodes = set()
        self.node_definitions = []
        self.relationships = []
        self.sparql_constraints = {}
        
    def parse_shacl_file(self, file_path: str) -> Graph:
        """Load and parse a SHACL file into an RDF graph."""
        g = Graph()
        g.parse(file_path)
        return g
        
    def extract_sparql_patterns(self, query_str: str) -> List[Dict]:
        """Extract patterns from a SPARQL query string."""
        patterns = []
        
        # Remove comments and normalize whitespace
        query_str = re.sub(r'#.*$', '', query_str, flags=re.MULTILINE)
        query_str = ' '.join(query_str.split())
        
        # Extract WHERE clause
        where_match = re.search(r'WHERE\s*{([^}]+)}', query_str, re.IGNORECASE)
        if where_match:
            where_clause = where_match.group(1).strip()
            
            # Split into triple patterns
            triple_patterns = re.findall(r'(?:[?]\w+|\<[^>]+\>|\w+:\w+)\s+(?:[?]\w+|\<[^>]+\>|\w+:\w+)\s+(?:[?]\w+|\<[^>]+\>|\w+:\w+|\".+?\")', where_clause)
            
            for pattern in triple_patterns:
                parts = pattern.strip().split()
                patterns.append({
                    'subject': parts[0],
                    'predicate': parts[1],
                    'object': parts[2]
                })
                
        return patterns

    def normalize_uri(self, uri: str) -> str:
        """Normalize URI representation for Mermaid."""
        if uri.startswith('?'):
            return uri[1:]
        elif uri.startswith('<') and uri.endswith('>'):
            return uri[1:-1].split('/')[-1]
        elif ':' in uri:
            return uri.split(':')[1]
        return uri

    def process_shape(self, g: Graph, shape_node: URIRef) -> None:
        """Process a SHACL shape node and generate Mermaid components."""
        if shape_node in self.seen_nodes:
            return
            
        self.seen_nodes.add(shape_node)
        shape_id = self.normalize_uri(str(shape_node))
        
        # Process basic shape properties
        target_class = g.value(shape_node, SH.targetClass)
        if target_class:
            class_name = self.normalize_uri(str(target_class))
            self.node_definitions.append(f"class {class_name}")
            self.relationships.append(f"{shape_id} --> {class_name} : validates")

        # Process SPARQL constraints
        for constraint in g.objects(shape_node, SH.sparql):
            select = g.value(constraint, SH.select)
            if select:
                patterns = self.extract_sparql_patterns(str(select))
                constraint_id = hashlib.md5(str(select).encode()).hexdigest()[:8]
                
                for pattern in patterns:
                    subj = self.normalize_uri(pattern['subject'])
                    pred = self.normalize_uri(pattern['predicate'])
                    obj = self.normalize_uri(pattern['object'])
                    
                    # Add nodes if they don't exist
                    if not any(subj in node for node in self.node_definitions):
                        self.node_definitions.append(f"class {subj}")
                    if not any(obj in node for node in self.node_definitions):
                        self.node_definitions.append(f"class {obj}")
                        
                    # Add relationship
                    self.relationships.append(f"{subj} --> {obj} : {pred}")

        # Process property constraints
        property_shapes = list(g.objects(shape_node, SH.property))
        for prop in property_shapes:
            path = g.value(prop, SH.path)
            if path:
                path_name = self.normalize_uri(str(path))
                class_name = g.value(prop, SH['class'])
                
                if class_name:
                    target_class = self.normalize_uri(str(class_name))
                    if not any(target_class in node for node in self.node_definitions):
                        self.node_definitions.append(f"class {target_class}")
                    self.relationships.append(f"{shape_id} --> {target_class} : {path_name}")

    def generate_mermaid(self, g: Graph) -> str:
        """Generate complete Mermaid diagram from SHACL shapes."""
        # Process all shape nodes
        for shape in g.subjects(RDF.type, SH.NodeShape):
            self.process_shape(g, shape)
            
        # Build Mermaid output
        mermaid = ["classDiagram"]
        mermaid.extend(self.node_definitions)
        mermaid.extend(self.relationships)
        
        return "\n    ".join(mermaid)

def convert_shacl_to_mermaid(shacl_file: str) -> str:
    """Convert a SHACL file to Mermaid diagram."""
    converter = SHACLToMermaid()
    graph = converter.parse_shacl_file(shacl_file)
    return converter.generate_mermaid(graph)

# Example usage
if __name__ == "__main__":
    
    shacl_file = 'casestudy_compartmentarea/shapes.ttl'
    try:
        mermaid_diagram = convert_shacl_to_mermaid(shacl_file)
        print(mermaid_diagram)
        with open('casestudy_compartmentarea/mermaid.txt', 'w') as file:
            file.write(mermaid_diagram)
    except Exception as e:
        print(f"Error converting SHACL to Mermaid: {str(e)}")