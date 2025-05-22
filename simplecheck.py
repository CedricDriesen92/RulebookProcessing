from pyshacl import validate
from rdflib import Graph, Namespace, Literal, URIRef, RDF
import tempfile
import os

def main():
    # Create a temporary file to store the inferred data
    with tempfile.NamedTemporaryFile(delete=False, suffix='.ttl') as tmp:
        tmp_file = tmp.name
    
    # Load the data and shapes from local files
    conforms, results_graph, results_text = validate(
        data_graph='IFCtoTTLin-outputs/Kortrijk_ED_IFC_architecture.ttl',
        shacl_graph='casestudy_compartmentarea/shapes.ttl',
        inference='rdfs',
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
        #debug=True,
        inplace=False,
        # Don't serialize the report graph
        serialize_report_graph=None
    )

    # Save the results graph to our temporary file
    results_graph.serialize(destination=tmp_file, format='turtle')

    # Print whether the data conforms to the shapes
    print("Conforms:", conforms)
    print("Results:")
    print(results_text)
    
    # Load the original data
    g = Graph()
    g.parse('IFCtoTTLin-outputs/Kortrijk_ED_IFC_architecture.ttl', format='turtle')
    
    # Define namespaces
    fbo = Namespace("https://ontology.firebim.be/ontology/fbo#")
    bpo = Namespace("https://w3id.org/bpo#")
    
    # Count compartments
    compartments = list(g.subjects(predicate=RDF.type, object=fbo.Compartment))
    print(f"\nFound {len(compartments)} compartments")
    
    # Check for spaces with hasCompartment relationship
    spaces_with_compartments = list(g.subjects(predicate=bpo.hasCompartment, object=None))
    print(f"Found {len(spaces_with_compartments)} spaces with compartment relationships")
    
    # Check if these spaces have Area properties
    spaces_with_area = 0
    spaces_without_area = 0
    
    for space in spaces_with_compartments:
        areas = list(g.objects(subject=space, predicate=bpo.Area))
        if areas:
            spaces_with_area += 1
        else:
            spaces_without_area += 1
    
    print(f"Spaces with compartments that have Area: {spaces_with_area}")
    print(f"Spaces with compartments that don't have Area: {spaces_without_area}")
    
    # Check a specific compartment in detail
    if compartments:
        # Take the first compartment as an example
        example_comp = compartments[0]
        comp_name = list(g.objects(subject=example_comp, predicate=bpo.name))[0] if list(g.objects(subject=example_comp, predicate=bpo.name)) else "Unknown"
        
        print(f"\nExamining spaces connected to compartment: {comp_name}")
        
        # Find spaces connected to this compartment
        connected_spaces = list(g.subjects(predicate=bpo.hasCompartment, object=example_comp))
        print(f"  Found {len(connected_spaces)} connected spaces")
        
        # Check the areas of these spaces
        spaces_with_area_count = 0
        total_area = 0
        
        for space in connected_spaces:
            space_areas = list(g.objects(subject=space, predicate=bpo.Area))
            if space_areas:
                spaces_with_area_count += 1
                try:
                    space_area = float(space_areas[0])
                    total_area += space_area
                    print(f"  Space {space}: Area = {space_area}")
                except ValueError:
                    print(f"  Space {space}: Area = {space_areas[0]} (not a valid number)")
            else:
                print(f"  Space {space}: No Area property")
        
        print(f"  {spaces_with_area_count} out of {len(connected_spaces)} spaces have Area properties")
        print(f"  Total area of all spaces: {total_area}")
        
        # Now let's try to manually execute the SPARQL query from our SHACL rule
        print("\nExecuting SPARQL query manually:")
        
        query = """
        PREFIX fbo: <http://example.org/ontology/fbo#>
        PREFIX bpo: <https://w3id.org/bpo#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        
        SELECT ?compartment (SUM(xsd:decimal(?area)) as ?totalArea) (COUNT(?space) as ?spaceCount)
        WHERE {
          ?compartment a fbo:Compartment .
          ?space bpo:hasCompartment ?compartment .
          ?space bpo:Area ?area .
        }
        GROUP BY ?compartment
        """
        
        results = g.query(query)
        print(f"Query returned {len(results)} results")
        
        for row in results:
            comp = row['compartment']
            total = row['totalArea']
            count = row['spaceCount']
            
            comp_name = list(g.objects(subject=comp, predicate=bpo.name))[0] if list(g.objects(subject=comp, predicate=bpo.name)) else "Unknown"
            print(f"  Compartment {comp_name}: Total Area = {total} (from {count} spaces)")
            
            if float(total) >= 3500:
                print(f"  *** {comp_name} exceeds the 3500 limit! ***")
    
    # Clean up the temporary file
    try:
        os.unlink(tmp_file)
    except:
        pass

if __name__ == "__main__":
    main()
