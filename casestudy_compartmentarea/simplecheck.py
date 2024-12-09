from pyshacl import validate

def main():
    # Load the data and shapes from local files
    conforms, results_graph, results_text = validate(
        data_graph='casestudy_compartmentarea/building.ttl',
        shacl_graph='casestudy_compartmentarea/shapes.ttl',
        inference='rdfs',       # enable RDFS inference if needed
        abort_on_first=False,
        meta_shacl=False,
        advanced=True
    )

    # Print whether the data conforms to the shapes
    print("Conforms:", conforms)
    # Print the detailed validation report
    print("Results:")
    print(results_text)

if __name__ == "__main__":
    main()
