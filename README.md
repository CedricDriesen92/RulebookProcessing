Parsing rulebook pdf's into a linked data format following a document ontology, and processing this .ttl into a viewable html reader. Building + SHACL tests using a new building ontology, with the resulting html linking to the rulebook.

- ParseRulebook.py: turn pdf into separate .ttl files (per section/subsection/subsubsection, stored in 'sections') according to FireBIM_Document_Ontology.ttl.
Done by LLM (3.5 Sonnet works the best) by loading already done examples and using a multi-shot approach. Samples are loaded from trainingsamplesRuleToGraph, all .ttl files are matched with their input .txt file.
Final result is stored in combined_document_data_graph.ttl.

- GraphToHTML.py: turn the combined graph from ParseRulebook into a nice-ish HTML viewer including layout, document tree, search bar, figures/tables, internal/external references...

- ParseRulesToSHACL.py: in the future should turn the combined document graph into shacl shapes. TODO.
For now does a simple check using a sample data graph (buildinggraphs/Article2_1_1BE_Data.ttl) and a SHACL representation of Article 2.1.1 (shaclshapes/Article2_1_1BE_Shapes.ttl).
Output is parsed into validation_report with the violation, severity, and node (entity) in violation. Also given is the original text of the document graph sourcing the rule, as well as a direct link to that text in the html from graphtohtml.py.
