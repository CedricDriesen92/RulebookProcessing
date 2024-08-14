Parsing rulebook pdf's into a linked data format following a document ontology, and processing this .ttl into a viewable html reader. Building + SHACL tests using a new building ontology, with the resulting html linking to the rulebook. Finally IFC to LBD is in a testing phase, rules to SHACL is TODO.

- DocumentPDFtoTTL.py: turn pdf into separate .ttl files (per section/subsection/subsubsection, stored in 'sections') according to FireBIM_Document_Ontology.ttl.
Done by LLM (3.5 Sonnet works the best) by loading already done examples and using a multi-shot approach. Samples are loaded from trainingsamplesRuleToGraph, all .ttl files are matched with their input .txt file.
Final result (combination of all the .ttl files in 'sections') is stored in combined_document_data_graph.ttl.

- DocumentTTLtoHTML.py: turn the combined graph from ParseRulebook into a nice-ish HTML viewer including layout, document tree, search bar, figures/tables, internal/external references, references to the related SHACL shapes (see next python file)...
![htmlvspdf](https://github.com/user-attachments/assets/212d6412-e557-4001-9aab-dd8703513739)

- RunSHACLonTTL.py: For now does a simple check using a sample data graph (buildinggraphs/Article2_1_1BE_Data.ttl) and a SHACL representation of Article 2.1.1 (shaclshapes/Article2_1_1BE_Shapes.ttl), both following the firebim building ontology defined in buildingontologies/firebimSource.ttl.
Output is parsed into validation_report.html with the violation, severity, and node (entity) in violation. Also given is the original text of the document graph sourcing the rule, as well as a direct link to that text in the html from graphtohtml.py. CREATION OF BOTH GRAPHS WAS DONE BY HAND.
![validationreport](https://github.com/user-attachments/assets/e8dd0691-8196-417e-b005-7f8407703872)

- IFCtoBuildingTTL.py: turn all .ifc files from the IFCtoTTLin-outputs path into .ttl files according to what should become the firebim building ontology. Includes a simple test for external door width for now.

- DocumentTTLtoSHACL.py: automatically creates SHACL shapes from the separate .ttl files in the /sections folder. TODO, and just a POC.