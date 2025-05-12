import sys
from rdflib import Graph, Namespace, URIRef, RDFS, RDF, Literal
from rdflib.term import BNode

# Define namespaces
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
FIREBIM = Namespace("http://example.com/firebim#") # Example custom namespace
FBB = Namespace("http://example.com/firebimbuilding#") # Example custom namespace

# New list for markers at different indentation levels
LIST_MARKERS = ["- ", "• ", "◆ ", "◇ "] 

# Friendly names for common URIs
FRIENDLY_URI_NAMES = {
    str(SH.IRI): "a Resource (IRI)",
    str(SH.BlankNode): "a Blank Node",
    str(SH.Literal): "a Literal value",
    str(SH.BlankNodeOrIRI): "a Resource or Blank Node",
    str(SH.BlankNodeOrLiteral): "a Blank Node or Literal",
    str(SH.IRIOrLiteral): "a Resource or Literal",
    str(XSD.string): "a String",
    str(XSD.integer): "an Integer",
    str(XSD.decimal): "a Decimal",
    str(XSD.double): "a Double",
    str(XSD.float): "a Float",
    str(XSD.boolean): "a Boolean (true/false)",
    str(XSD.date): "a Date (YYYY-MM-DD)",
    str(XSD.dateTime): "a DateTime (YYYY-MM-DDTHH:mm:ss)",
    str(XSD.time): "a Time (HH:mm:ss)",
    # Add more as needed
}

def format_line(level: int, text: str) -> str:
    """Formats a line with appropriate indentation and symbol."""
    prefix = ""
    if level == 0:
        # No indentation or marker for level 0
        prefix = ""
    elif level == 1:
        # Level 1 is just a single tab indent
        prefix = "\t"
    elif level >= 2:
        # Levels 2 and above get (level) tabs and a marker
        # Marker index cycles through LIST_MARKERS
        # Level 2 gets marker_idx 0, Level 3 gets 1, etc.
        marker_idx = (level - 2) % len(LIST_MARKERS)
        prefix = ("\t" * level) + LIST_MARKERS[marker_idx]
    
    return prefix + text

def get_friendly_uri_name(graph, uri_ref, ontology_graph):
    """Gets a human-friendly label for a URI, with fallbacks."""
    if not isinstance(uri_ref, URIRef):
        return str(uri_ref) # Literals, BNodes

    uri_str = str(uri_ref)
    if uri_str in FRIENDLY_URI_NAMES:
        return FRIENDLY_URI_NAMES[uri_str]

    # Check for rdfs:label in the ontology_graph first
    for label_obj in ontology_graph.objects(uri_ref, RDFS.label):
        label_str = str(label_obj)
        if label_str.strip(): # Only return if non-empty
            return label_str

    # Then in the shapes_graph (e.g., for sh:name on shapes)
    for label_obj in graph.objects(uri_ref, RDFS.label):
        label_str = str(label_obj)
        if label_str.strip(): # Only return if non-empty
            return label_str

    for name_obj in graph.objects(uri_ref, SH.name): # sh:name is also good
        name_str = str(name_obj)
        if name_str.strip(): # Only return if non-empty
            return name_str

    # Fallback to local name
    try:
        # QName local part
        qname_tuple = graph.namespace_manager.compute_qname(uri_ref)
        local_part_qname = qname_tuple[2]
        if local_part_qname.strip(): # Ensure local part is not empty
            return local_part_qname
    except Exception: # Broad exception because compute_qname can fail in various ways
        # Fallback parsing of URI string if compute_qname fails
        pass

    if "#" in uri_str:
        local_part_hash = uri_str.split("#")[-1]
        if local_part_hash.strip():
            return local_part_hash

    local_part_slash = uri_str.rsplit("/", 1)[-1]
    if local_part_slash.strip(): # Check if this part is non-empty
        return local_part_slash

    return uri_str # Absolute URI as last resort if all else fails or results in empty

def rdf_list_to_python_list(graph, list_node):
    """Converts an RDF list (rdf:first/rdf:rest*) to a Python list."""
    items = []
    current = list_node
    while current and current != RDF.nil:
        first_item = list(graph.objects(current, RDF.first))
        if first_item:
            items.append(first_item[0])
        rest_item = list(graph.objects(current, RDF.rest))
        current = rest_item[0] if rest_item else None
    return items

def describe_constraints_on_shape(shapes_graph, ontology_graph, shape_uri, indent_level, is_property_context=False):
    """
    Describes all constraints present on a given shape_uri.
    This is the core recursive function for describing shape contents.
    """
    descriptions = []
    processed_constraints = set() # To avoid re-processing if sh:message covers it

    # 0. Handle sh:message, sh:name, sh:description on the shape_uri itself
    shape_name = get_friendly_uri_name(shapes_graph, shape_uri, ontology_graph)
    for msg_literal in shapes_graph.objects(shape_uri, SH.message):
        if not is_property_context or (SH["if"] in processed_constraints or SH["then"] in processed_constraints or SH["else"] in processed_constraints) :
             descriptions.append(format_line(indent_level+1, f"(Comment: {str(msg_literal)})"))
        processed_constraints.add(SH.message)

    if not is_property_context and not isinstance(shape_uri, BNode):
        for name_literal in shapes_graph.objects(shape_uri, SH.name):
            pass
        for desc_literal in shapes_graph.objects(shape_uri, SH.description):
            descriptions.append(format_line(indent_level, f"Description: {str(desc_literal)}"))

    # 1. Property Constraints (sh:property)
    if SH.property not in processed_constraints:
        for prop_shape_uri_inner in shapes_graph.objects(shape_uri, SH.property):
            descriptions.extend(describe_property_constraints(shapes_graph, ontology_graph, prop_shape_uri_inner, indent_level +1))
        if list(shapes_graph.objects(shape_uri, SH.property)):
            processed_constraints.add(SH.property)

    # 2. Logical Constraints (sh:and, sh:or, sh:not, sh:xone)
    logical_ops = {
        SH["and"]: "ALL of the following must be true:",
        SH["or"]: "AT LEAST ONE of the following must be true:",
        SH.xone: "EXACTLY ONE of the following must be true:",
    }
    for op_pred, op_message in logical_ops.items():
        if op_pred not in processed_constraints:
            op_lists = list(shapes_graph.objects(shape_uri, op_pred))
            if op_lists:
                descriptions.append(format_line(indent_level + 0, op_message))
                shapes_in_list = rdf_list_to_python_list(shapes_graph, op_lists[0])
                for i, sub_shape_uri_in_list in enumerate(shapes_in_list):
                    current_indent_for_sub_shape = indent_level + (2 if op_pred == SH["or"] or op_pred == SH.xone else 2)
                    if op_pred == SH["or"] or op_pred == SH.xone:
                         descriptions.append(format_line(indent_level + 1, f"Option {i+1}:"))
                    descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, sub_shape_uri_in_list, current_indent_for_sub_shape, is_property_context=False ))
                processed_constraints.add(op_pred)

    if SH["not"] not in processed_constraints:
        not_shapes = list(shapes_graph.objects(shape_uri, SH["not"]))
        if not_shapes:
            descriptions.append(format_line(indent_level + 0, "The following conditions must NOT be met:"))
            descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, not_shapes[0], indent_level + 1, is_property_context=False))
            processed_constraints.add(SH["not"])
        
    # 3. Node Constraints (sh:node - links to another shape)
    if SH.node not in processed_constraints:
        for linked_node_shape_uri in shapes_graph.objects(shape_uri, SH.node):
            linked_shape_name = get_friendly_uri_name(shapes_graph, linked_node_shape_uri, ontology_graph)
            descriptions.append(format_line(indent_level + 0, f"Must also conform to shape: {linked_shape_name}."))
        if list(shapes_graph.objects(shape_uri, SH.node)):
            processed_constraints.add(SH.node)

    # 3.5 Direct Shape Constraints (sh:class, sh:datatype, sh:nodeKind)
    # Create explicit URIRef objects for direct constraints to avoid naming issues
    SH_CLASS = URIRef("http://www.w3.org/ns/shacl#class")
    SH_DATATYPE = URIRef("http://www.w3.org/ns/shacl#datatype") 
    SH_NODEKIND = URIRef("http://www.w3.org/ns/shacl#nodeKind")

    direct_constraint_predicates_to_describe = {
        SH_CLASS: ("Must be an instance of {label}.", "Values must be an instance of {label}."),
        SH_DATATYPE: ("Must be of datatype {label}.", "Values must be of datatype {label}."),
        SH_NODEKIND: ("Must be {label}.", "Values must be {label}.")
    }

    # For each type of direct constraint we want to describe (e.g., SH.class_, then SH.datatype_, etc.)
    for pred_key_from_map, (text_template_node, text_template_prop_value) in direct_constraint_predicates_to_describe.items():
        
        # Check if this general type of constraint (e.g., SH.class_) has already been processed for this shape_uri
        if pred_key_from_map in processed_constraints:
            continue

        found_and_processed_this_type = False
        # Iterate ALL outgoing triples from the current shape_uri
        for s_graph, p_graph, o_graph in shapes_graph.triples((shape_uri, None, None)):
            # We are only interested in triples where the subject is the current shape_uri
            # and the predicate is the specific one we are looking for in this iteration (pred_key_from_map)
            if s_graph == shape_uri and p_graph == pred_key_from_map:
                print(f"MATCH! Triple: {s_graph} {p_graph} {o_graph}")  # Add this temporary debug line
                
                label = get_friendly_uri_name(shapes_graph, o_graph, ontology_graph)
                if label and label.strip(): # Ensure label is not empty
                    text_to_add = ""
                    if is_property_context:
                        text_to_add = text_template_prop_value.format(label=label)
                    else:
                        text_to_add = text_template_node.format(label=label)
                    
                    if text_to_add.strip():
                        descriptions.append(format_line(indent_level, text_to_add))
                        found_and_processed_this_type = True
        
        # If we found and described any instances of this constraint type (e.g., SH.class_),
        # mark it as processed so other parts of the code don't try to re-process it.
        if found_and_processed_this_type:
            processed_constraints.add(pred_key_from_map)

    # 4. SPARQL Constraints and Rules
    # sh:sparql (validation constraint)
    if SH.sparql not in processed_constraints:
        for sparql_constraint_node in shapes_graph.objects(shape_uri, SH.sparql):
            msgs = list(shapes_graph.objects(sparql_constraint_node, SH.message))
            if msgs:
                descriptions.append(format_line(indent_level + 1, f"SPARQL Validation: {str(msgs[0])}"))
            else:
                select_query = list(shapes_graph.objects(sparql_constraint_node, SH.select))
                ask_query = list(shapes_graph.objects(sparql_constraint_node, SH.ask))
                if select_query:
                    descriptions.append(format_line(indent_level + 1, f"Custom SPARQL validation (select query must return no results):"))
                elif ask_query:
                    descriptions.append(format_line(indent_level + 1, f"Custom SPARQL validation (ask query must return false):"))
                else:
                    descriptions.append(format_line(indent_level + 1, "Has an unspecified SPARQL constraint."))
            severity = list(shapes_graph.objects(sparql_constraint_node, SH.severity))
            if severity:
                descriptions.append(format_line(indent_level + 2, f"(Severity: {get_friendly_uri_name(shapes_graph, severity[0], ontology_graph)})"))
        if list(shapes_graph.objects(shape_uri, SH.sparql)):
             processed_constraints.add(SH.sparql)

    # sh:rule (inference rule)
    if SH.rule not in processed_constraints:
        for rule_node in shapes_graph.objects(shape_uri, SH.rule):
            if (rule_node, RDF.type, SH.SPARQLRule) in shapes_graph:
                msgs = list(shapes_graph.objects(rule_node, SH.message))
                if msgs:
                    descriptions.append(format_line(indent_level + 1, f"SPARQL Inference Rule: {str(msgs[0])}"))
                else:
                    construct_query = list(shapes_graph.objects(rule_node, SH.construct))
                    if construct_query:
                        descriptions.append(format_line(indent_level + 1, "Has SPARQL inference rule (constructs new data):"))
                    else:
                        descriptions.append(format_line(indent_level + 1, "Has an unspecified SPARQL inference rule."))
        if list(shapes_graph.objects(shape_uri, SH.rule)):
            processed_constraints.add(SH.rule)

    # 5. sh:closed and sh:ignoredProperties
    if SH.closed not in processed_constraints:
        closed_values = list(shapes_graph.objects(shape_uri, SH.closed))
        if closed_values and str(closed_values[0]).lower() == 'true':
            ignored_props_list_node = list(shapes_graph.objects(shape_uri, SH.ignoredProperties))
            if ignored_props_list_node:
                ignored_props = [get_friendly_uri_name(shapes_graph, p, ontology_graph) for p in rdf_list_to_python_list(shapes_graph, ignored_props_list_node[0])]
                descriptions.append(format_line(indent_level + 1, f"Must not have properties other than those explicitly allowed or listed as ignored: {', '.join(ignored_props)}."))
            else:
                descriptions.append(format_line(indent_level + 1, "Must not have properties other than those explicitly allowed by sh:property constraints."))
            processed_constraints.add(SH.closed)

    return descriptions


def describe_property_constraints(shapes_graph, ontology_graph, prop_shape_uri, indent_level):
    """
    Describes constraints specific to a property shape (those that use sh:path).
    """
    descriptions = []
    path_nodes = list(shapes_graph.objects(prop_shape_uri, SH.path))
    if not path_nodes:
        # This might be a BNode with constraints but no path, handled by describe_constraints_on_shape
        descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, prop_shape_uri, indent_level, is_property_context=True))
        return descriptions

    prop_uri = path_nodes[0]
    prop_label = get_friendly_uri_name(shapes_graph, prop_uri, ontology_graph)
    base_property_text = f"Property '{prop_label}'"

    # Overall message for the property shape
    for msg in shapes_graph.objects(prop_shape_uri, SH.message):
        descriptions.append(format_line(indent_level, f"{base_property_text}: {str(msg)}"))
        # If a general message exists, we might skip detailed ones, or show them as "Additionally..."
        # For now, we show both.

    # Detailed constraints
    constraints_found = False

    # Min/Max Count
    for pred, template_val in [(SH.minCount, "at least {value}"), (SH.maxCount, "at most {value}")]:
        for val_node in shapes_graph.objects(prop_shape_uri, pred): # val_node could be Literal or BNode
            msg = None
            actual_value = val_node
            if isinstance(val_node, BNode): # Check for sh:message on constraint component BNode
                for m in shapes_graph.objects(val_node, SH.message): msg = str(m)
                for v in shapes_graph.objects(val_node, RDF.value): actual_value = v # SHACL Core an RDF.value for value

            if msg:
                descriptions.append(format_line(indent_level, f"{base_property_text}: {msg}"))
            else:
                descriptions.append(format_line(indent_level, f"{base_property_text} must appear {template_val.format(value=str(actual_value))} time(s)."))
            constraints_found = True

    # Datatype
    for dt_uri in shapes_graph.objects(prop_shape_uri, SH.datatype):
        dt_label = get_friendly_uri_name(shapes_graph, dt_uri, ontology_graph)
        descriptions.append(format_line(indent_level, f"{base_property_text} must be of datatype {dt_label}."))
        constraints_found = True

    # NodeKind
    for nk_uri in shapes_graph.objects(prop_shape_uri, SH.nodeKind):
        nk_label = get_friendly_uri_name(shapes_graph, nk_uri, ontology_graph)
        descriptions.append(format_line(indent_level, f"{base_property_text} must be {nk_label}."))
        constraints_found = True

    # Class (sh:class)
    for class_uri in shapes_graph.objects(prop_shape_uri, SH.class_):
        class_label = get_friendly_uri_name(shapes_graph, class_uri, ontology_graph)
        descriptions.append(format_line(indent_level, f"{base_property_text} must be an instance of {class_label}."))
        constraints_found = True

    # Value range (min/max Inclusive/Exclusive)
    range_constraints = {
        SH.minInclusive: "must be at least {value}.",
        SH.maxInclusive: "must be at most {value}.",
        SH.minExclusive: "must be greater than {value}.",
        SH.maxExclusive: "must be less than {value}.",
    }
    for pred, template in range_constraints.items():
        for val in shapes_graph.objects(prop_shape_uri, pred):
            descriptions.append(format_line(indent_level, f"{base_property_text} {template.format(value=str(val))}"))
            constraints_found = True

    # String specific (min/maxLength, pattern)
    str_constraints = {
        SH.minLength: "must have a minimum length of {value}.",
        SH.maxLength: "must have a maximum length of {value}.",
        SH.pattern: "must match the pattern: '{value}'.",
    }
    for pred, template in str_constraints.items():
        for val_node in shapes_graph.objects(prop_shape_uri, pred): # val_node could be Literal or BNode
            msg = None
            actual_value = val_node
            if isinstance(val_node, BNode):
                for m in shapes_graph.objects(val_node, SH.message): msg = str(m)
                for v in shapes_graph.objects(val_node, RDF.value): actual_value = v
            
            flags = ""
            if pred == SH.pattern:
                 for f in shapes_graph.objects(prop_shape_uri, SH.flags): flags = f" (flags: {str(f)})"

            if msg:
                descriptions.append(format_line(indent_level, f"{base_property_text}: {msg}"))
            else:
                descriptions.append(format_line(indent_level, f"{base_property_text} {template.format(value=str(actual_value))}{flags}"))
            constraints_found = True


    # sh:hasValue
    for val_uri in shapes_graph.objects(prop_shape_uri, SH.hasValue):
        val_label = get_friendly_uri_name(shapes_graph, val_uri, ontology_graph)
        if isinstance(val_uri, Literal) and str(val_uri).lower() in ['true', 'false']:
            val_label = str(val_uri).lower()
        descriptions.append(format_line(indent_level, f"{base_property_text} must be exactly {val_label}."))
        constraints_found = True

    # sh:in (list of allowed values)
    for list_node in shapes_graph.objects(prop_shape_uri, SH.in_):
        allowed_values = [get_friendly_uri_name(shapes_graph, item, ontology_graph) for item in rdf_list_to_python_list(shapes_graph, list_node)]
        descriptions.append(format_line(indent_level, f"{base_property_text} must be one of: {', '.join(allowed_values)}."))
        constraints_found = True
    
    # If this property shape also has nested constraints (e.g. sh:node linking to another shape for values)
    # these are handled by describe_constraints_on_shape called on prop_shape_uri
    # We need to ensure we don't double-process basic property constraints handled above.
    # This means describe_constraints_on_shape needs to be aware if it's being called for a property.
    # The `is_property_context` flag in describe_constraints_on_shape helps with this.
    # Here, we call it to pick up sh:node, sh:and, sh:or etc. on the property shape itself.
    
    # Check if prop_shape_uri has constraints other than sh:path and basic ones already handled
    has_other_constraints_on_value = False
    for p, _ in shapes_graph.predicate_objects(prop_shape_uri):
        if p not in [SH.path, SH.message, SH.severity, SH.minCount, SH.maxCount, SH.datatype, SH.nodeKind, SH.class_,
                      SH.minInclusive, SH.maxInclusive, SH.minExclusive, SH.maxExclusive,
                      SH.minLength, SH.maxLength, SH.pattern, SH.flags, SH.hasValue, SH.in_]:
            has_other_constraints_on_value = True # e.g. sh:node, sh:and, sh:or, sh:not, sh:xone on the property value's shape
            break
    
    if has_other_constraints_on_value:
        # Get descriptions for non-path specific constraints on the property shape's values
        # These constraints apply to what the values of 'prop_label' must conform to.
        # The recursive call should be at the next indent level.
        nested_constraints_indent_level = indent_level + 1
        value_shape_constraints = describe_constraints_on_shape(
            shapes_graph, ontology_graph, 
            prop_shape_uri, 
            nested_constraints_indent_level, 
            is_property_context=True
        )
        
        if value_shape_constraints:
            # Print the header only if there are actual sub-constraints to list.
            # This header is at the parent's indent_level.
            descriptions.append(format_line(indent_level, f"Additionally, values of '{prop_label}' must satisfy:"))
            
            for d_line in value_shape_constraints:
                # d_line is already fully formatted with the correct indentation 
                # (nested_constraints_indent_level) by the recursive call.
                # We just append it directly.
                if d_line.strip(): # Avoid adding empty or whitespace-only lines
                    descriptions.append(d_line)

    # Severity for the property shape
    for sev_uri in shapes_graph.objects(prop_shape_uri, SH.severity):
        sev_label = get_friendly_uri_name(shapes_graph, sev_uri, ontology_graph)
        # Add to last relevant description or as a new line
        if descriptions:
            if "(Severity:" not in descriptions[-1]:
                 descriptions[-1] += f" (Severity: {sev_label})"
            else: # If last line already has severity, or if no constraints found yet
                 descriptions.append(format_line(indent_level, f"{base_property_text} (Severity: {sev_label})"))

        elif not constraints_found: # No specific constraints, just severity
            descriptions.append(format_line(indent_level, f"{base_property_text} has an overall severity: {sev_label}."))


    if not descriptions and not path_nodes: # BNode without path, likely part of sh:and/or
        return describe_constraints_on_shape(shapes_graph, ontology_graph, prop_shape_uri, indent_level, is_property_context=True)


    return descriptions


def describe_node_shape(shapes_graph, ontology_graph, node_shape_uri, indent_level=0):
    """
    Describes a top-level NodeShape.
    """
    descriptions = []
    shape_name = get_friendly_uri_name(shapes_graph, node_shape_uri, ontology_graph)

    # Basic info: Name, Target Class, Messages, Description
    if not isinstance(node_shape_uri, BNode): # Named shape
        descriptions.append(format_line(indent_level, f"Shape: {shape_name}"))
    else: # Blank node shape
        descriptions.append(format_line(indent_level, "Shape (Anonymous Node):"))
    indent_level += 1

    for name in shapes_graph.objects(node_shape_uri, SH.name):
        descriptions.append(format_line(indent_level, f"Name: {str(name)}"))
    for desc in shapes_graph.objects(node_shape_uri, SH.description):
        descriptions.append(format_line(indent_level, f"Description: {str(desc)}"))
    for msg in shapes_graph.objects(node_shape_uri, SH.message):
        descriptions.append(format_line(indent_level, f"Overall Message: {str(msg)}"))

    # Targets
    target_classes = list(shapes_graph.objects(node_shape_uri, SH.targetClass))
    if target_classes:
        class_labels = [get_friendly_uri_name(shapes_graph, tc, ontology_graph) for tc in target_classes]
        descriptions.append(format_line(indent_level, f"Applies to instances of: {', '.join(class_labels)}"))
    # Add other targets: sh:targetNode, sh:targetSubjectsOf, sh:targetObjectsOf if needed

    # Custom properties (like FIREBIM:rulesource, FBB:flowchartNodeID)
    custom_props_to_display = {
        FIREBIM.rulesource: "Rule source",
        FBB.flowchartNodeID: "Flowchart Node ID(s)"
    }
    for prop_uri, label_text in custom_props_to_display.items():
        values = list(shapes_graph.objects(node_shape_uri, prop_uri))
        if values:
            value_strs = [get_friendly_uri_name(shapes_graph, v, ontology_graph) for v in values]
            descriptions.append(format_line(indent_level, f"{label_text}: {', '.join(value_strs)}"))
    
    # Overall Severity for the NodeShape
    for sev_uri in shapes_graph.objects(node_shape_uri, SH.severity):
        sev_label = get_friendly_uri_name(shapes_graph, sev_uri, ontology_graph)
        descriptions.append(format_line(indent_level, f"Overall Severity: {sev_label}"))


    # Core constraints
    descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, node_shape_uri, indent_level))

    return descriptions


def shacl_to_text(shapes_file_path: str, ontology_file_path: str = None) -> list[str]:
    """
    Main function to process SHACL shapes and ontology, returning human-readable descriptions.
    """
    shapes_graph = Graph()
    shapes_graph.parse(shapes_file_path, format="turtle") # Assumes turtle, add format detection if needed

    ontology_graph = Graph()
    if ontology_file_path:
        try:
            ontology_graph.parse(ontology_file_path, format="turtle")
        except Exception as e:
            print(f"Warning: Could not parse ontology file {ontology_file_path}: {e}", file=sys.stderr)

    # Bind namespaces for nicer output if get_friendly_uri_name falls back to qname
    shapes_graph.bind("sh", SH)
    shapes_graph.bind("xsd", XSD)
    if FIREBIM: shapes_graph.bind("firebim", FIREBIM)
    if FBB: shapes_graph.bind("fbb", FBB)
    # You might want to bind namespaces from the ontology_graph as well

    all_descriptions = []
    node_shapes = set(shapes_graph.subjects(RDF.type, SH.NodeShape))
    
    # Also consider shapes that are subjects of sh:targetClass etc. but not explicitly typed NodeShape
    for s, p, o in shapes_graph.triples((None, SH.targetClass, None)):
        node_shapes.add(s)
    # Add more robust NodeShape discovery if needed

    if not node_shapes:
        return ["No NodeShapes found in the SHACL file."]

    sorted_node_shapes = sorted(list(node_shapes), key=lambda x: str(x)) # Sort for consistent output

    for ns_uri in sorted_node_shapes:
        # Filter out PropertyShapes that might also be typed as NodeShape (less common but possible)
        # A primary NodeShape typically won't have sh:path directly.
        if (ns_uri, SH.path, None) in shapes_graph and not any(shapes_graph.objects(ns_uri, SH.targetClass)):
            # This looks more like a PropertyShape that might have been accidentally typed as NodeShape
            # or is a shape used within sh:node. Skip describing it as a top-level NodeShape.
            continue

        all_descriptions.append(f"\n--- Constraints for NodeShape: {get_friendly_uri_name(shapes_graph, ns_uri, ontology_graph)} ---")
        shape_descriptions = describe_node_shape(shapes_graph, ontology_graph, ns_uri)
        all_descriptions.extend(shape_descriptions)
        all_descriptions.append("") # Blank line for readability

    return all_descriptions

if __name__ == "__main__":
    # Example usage with proper path formatting
    shapes_file = r"shacl/BasisnormenLG_cropped.pdf/shape_Article_Article_2_1_1.ttl"
    ontology_file = r"casestudy_compartmentarea/fbb.ttl"
    output_file = r"temp_output_shacltotxt.txt"
    descriptions = shacl_to_text(shapes_file, ontology_file)

    with open(output_file, "w", encoding="utf-8") as f:
        for line in descriptions:
            f.write(line + "\n")
            print(line)

    print(f"\nOutput written to {output_file}")