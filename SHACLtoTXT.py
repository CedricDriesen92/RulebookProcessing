import sys
import tkinter as tk
from tkinter import scrolledtext, font, PanedWindow
import re
from rdflib import Graph, Namespace, URIRef, RDFS, RDF, Literal
from rdflib.term import BNode

# Define namespaces
SH = Namespace("http://www.w3.org/ns/shacl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
FIREBIM = Namespace("http://example.com/firebim#") # Example custom namespace
FBB = Namespace("http://example.com/firebimbuilding#") # Example custom namespace

# New list for markers at different indentation levels
# LIST_MARKERS = ["- ", "• ", "◆ ", "◇ "] # Removed for Markdown

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
    """Formats a line with appropriate Markdown indentation and list markers."""
    if level == 0: # For headings or text that shouldn't be a list item
        return text
    # For list items, level 1 is a top-level list, level 2+ are nested.
    # Markdown uses spaces for indentation of nested lists.
    # A common practice is 2 spaces per indent level for sub-lists.
    # The list marker itself is typically "- " or "* ".
    indent_spaces = "  " * (level - 1) if level > 0 else ""
    return f"{indent_spaces}- {text}"

def get_friendly_uri_name(graph, uri_ref, ontology_graph):
    """Gets a human-friendly label for a URI, with fallbacks."""
    if not isinstance(uri_ref, URIRef):
        return str(uri_ref) # Literals, BNodes

    uri_str = str(uri_ref)
    if uri_str in FRIENDLY_URI_NAMES:
        return FRIENDLY_URI_NAMES[uri_str]

    # Check for rdfs:label in the ontology_graph first
    if ontology_graph: # Check if ontology_graph is not None and has data
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
    #for msg_literal in shapes_graph.objects(shape_uri, SH.message):
    #    if not is_property_context or (SH["if"] in processed_constraints or SH["then"] in processed_constraints or SH["else"] in processed_constraints) :
    #         descriptions.append(format_line(indent_level+1, f"(Comment: {str(msg_literal)})"))
    #    processed_constraints.add(SH.message)

    #if not is_property_context and not isinstance(shape_uri, BNode):
    #    for name_literal in shapes_graph.objects(shape_uri, SH.name):
    #        pass
    #    for desc_literal in shapes_graph.objects(shape_uri, SH.description):
    #        descriptions.append(format_line(indent_level, f"Description: {str(desc_literal)}"))

    # 1. Property Constraints (sh:property)
    if SH.property not in processed_constraints:
        for prop_shape_uri_inner in shapes_graph.objects(shape_uri, SH.property):
            # Property constraints will start at the current indent_level as list items
            descriptions.extend(describe_property_constraints(shapes_graph, ontology_graph, prop_shape_uri_inner, indent_level))
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
                # The logical operator message itself is a list item.
                descriptions.append(format_line(indent_level, f"**{op_message}**"))
                shapes_in_list = rdf_list_to_python_list(shapes_graph, op_lists[0])
                # Sub-shapes/conditions are nested list items.
                sub_indent_level = indent_level + 1
                for i, sub_shape_uri_in_list in enumerate(shapes_in_list):
                    if op_pred == SH["or"] or op_pred == SH.xone:
                         descriptions.append(format_line(sub_indent_level, f"**Option {i+1}:**"))
                         # Constraints for the option are further nested.
                         descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, sub_shape_uri_in_list, sub_indent_level + 1, is_property_context=False ))
                    else: # for sh:and
                        descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, sub_shape_uri_in_list, sub_indent_level, is_property_context=False ))
                processed_constraints.add(op_pred)

    if SH["not"] not in processed_constraints:
        not_shapes = list(shapes_graph.objects(shape_uri, SH["not"]))
        if not_shapes:
            descriptions.append(format_line(indent_level, "**The following conditions must NOT be met:**"))
            # Constraints under sh:not are nested.
            descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, not_shapes[0], indent_level + 1, is_property_context=False))
            processed_constraints.add(SH["not"])
        
    # 3. Node Constraints (sh:node - links to another shape)
    if SH.node not in processed_constraints:
        node_shape_links = list(shapes_graph.objects(shape_uri, SH.node))
        if node_shape_links:
            linked_shape_constraints_start_indent = indent_level + 1

            for linked_node_shape_uri in node_shape_links:
                if not is_property_context:
                    linked_shape_friendly_name = get_friendly_uri_name(shapes_graph, linked_node_shape_uri, ontology_graph)
                    header_text = ""
                    if isinstance(linked_node_shape_uri, BNode):
                        header_text = "The value must conform to an **embedded shape** with the following constraints:"
                    else:
                        header_text = f"The value must also conform to shape **'{linked_shape_friendly_name}'**, which has the following constraints:"
                    descriptions.append(format_line(indent_level, f"**{header_text}**"))
                
                descriptions.extend(describe_constraints_on_shape(
                    shapes_graph, ontology_graph, 
                    linked_node_shape_uri, 
                    linked_shape_constraints_start_indent, 
                    is_property_context=False 
                ))
            if node_shape_links: 
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
                # print(f"MATCH! Triple: {s_graph} {p_graph} {o_graph}") # Keep commented or remove
                
                label = get_friendly_uri_name(shapes_graph, o_graph, ontology_graph)
                if label and label.strip(): # Ensure label is not empty
                    text_to_add = ""
                    if is_property_context:
                        text_to_add = text_template_prop_value.format(label=f"**{label}**")
                    else:
                        text_to_add = text_template_node.format(label=f"**{label}**")
                    
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
            main_sparql_text = ""
            if msgs:
                main_sparql_text = f"**SPARQL Validation:** {str(msgs[0])}"
            else:
                select_query = list(shapes_graph.objects(sparql_constraint_node, SH.select))
                ask_query = list(shapes_graph.objects(sparql_constraint_node, SH.ask))
                if select_query:
                    main_sparql_text = "**Custom SPARQL validation (select query must return no results):**"
                elif ask_query:
                    main_sparql_text = "**Custom SPARQL validation (ask query must return false):**"
                else:
                    main_sparql_text = "**Has an unspecified SPARQL constraint.**"
            descriptions.append(format_line(indent_level, main_sparql_text))
            
            severity = list(shapes_graph.objects(sparql_constraint_node, SH.severity))
            if severity:
                descriptions.append(format_line(indent_level + 1, f"Severity: **{get_friendly_uri_name(shapes_graph, severity[0], ontology_graph)}**"))
        if list(shapes_graph.objects(shape_uri, SH.sparql)):
             processed_constraints.add(SH.sparql)

    # sh:rule (inference rule)
    if SH.rule not in processed_constraints:
        for rule_node in shapes_graph.objects(shape_uri, SH.rule):
            if (rule_node, RDF.type, SH.SPARQLRule) in shapes_graph:
                msgs = list(shapes_graph.objects(rule_node, SH.message))
                rule_text = ""
                if msgs:
                    rule_text = f"**SPARQL Inference Rule:** {str(msgs[0])}"
                else:
                    construct_query = list(shapes_graph.objects(rule_node, SH.construct))
                    if construct_query:
                        rule_text = "**Has SPARQL inference rule (constructs new data):**"
                    else:
                        rule_text = "**Has an unspecified SPARQL inference rule.**"
                descriptions.append(format_line(indent_level, rule_text))
        if list(shapes_graph.objects(shape_uri, SH.rule)):
            processed_constraints.add(SH.rule)

    # 5. sh:closed and sh:ignoredProperties
    if SH.closed not in processed_constraints:
        closed_values = list(shapes_graph.objects(shape_uri, SH.closed))
        if closed_values and str(closed_values[0]).lower() == 'true':
            closed_text = ""
            ignored_props_list_node = list(shapes_graph.objects(shape_uri, SH.ignoredProperties))
            if ignored_props_list_node:
                ignored_props = [f"**{get_friendly_uri_name(shapes_graph, p, ontology_graph)}**" for p in rdf_list_to_python_list(shapes_graph, ignored_props_list_node[0])]
                closed_text = f"Must not have properties other than those explicitly allowed or listed as ignored: {', '.join(ignored_props)}."
            else:
                closed_text = "Must not have properties other than those explicitly allowed by `sh:property` constraints."
            descriptions.append(format_line(indent_level, closed_text))
            processed_constraints.add(SH.closed)

    return descriptions


def describe_property_constraints(shapes_graph, ontology_graph, prop_shape_uri, indent_level):
    """
    Describes constraints specific to a property shape (those that use sh:path).
    """
    descriptions = []
    path_nodes = list(shapes_graph.objects(prop_shape_uri, SH.path))
    
    prop_label_for_header = "Property (unknown path)" # Fallback
    if path_nodes:
        prop_uri = path_nodes[0]
        prop_label_for_header = get_friendly_uri_name(shapes_graph, prop_uri, ontology_graph)

    # Property header is a list item at the current indent_level
    descriptions.append(format_line(indent_level, f"**Property '{prop_label_for_header}'**"))
    
    # All subsequent constraints for this property will be nested one level deeper.
    constraint_detail_indent_level = indent_level + 1

    if not path_nodes:
        # This might be a BNode with constraints but no path, e.g. in sh:or list.
        # Its constraints are described directly, nested under the "Property (unknown path)" header.
        descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, prop_shape_uri, constraint_detail_indent_level, is_property_context=True))
        return descriptions

    # Re-fetch prop_uri and prop_label if we are sure path_nodes exist.
    prop_uri = path_nodes[0] # Already assigned if path_nodes is true.
    # prop_label = get_friendly_uri_name(shapes_graph, prop_uri, ontology_graph) # Already got as prop_label_for_header

    # Detailed constraints
    constraints_found_on_prop = False # Tracks if any specific constraint was added for *this* property shape.

    # Min/Max Count
    for pred, template_val in [(SH.minCount, "at least {value}"), (SH.maxCount, "at most {value}")]:
        for val_node in shapes_graph.objects(prop_shape_uri, pred): 
            msg = None
            actual_value = val_node
            if isinstance(val_node, BNode): 
                for m in shapes_graph.objects(val_node, SH.message): msg = str(m)
                for v in shapes_graph.objects(val_node, RDF.value): actual_value = v 

            if msg:
                descriptions.append(format_line(constraint_detail_indent_level, msg))
            else:
                descriptions.append(format_line(constraint_detail_indent_level, f"Must appear {template_val.format(value=f'**{str(actual_value)}**')} time(s)."))
            constraints_found_on_prop = True

    # Datatype
    for dt_uri in shapes_graph.objects(prop_shape_uri, SH.datatype):
        dt_label = get_friendly_uri_name(shapes_graph, dt_uri, ontology_graph)
        descriptions.append(format_line(constraint_detail_indent_level, f"Must be of datatype **{dt_label}**."))
        constraints_found_on_prop = True

    # NodeKind
    for nk_uri in shapes_graph.objects(prop_shape_uri, SH.nodeKind):
        nk_label = get_friendly_uri_name(shapes_graph, nk_uri, ontology_graph)
        descriptions.append(format_line(constraint_detail_indent_level, f"Must be **{nk_label}**."))
        constraints_found_on_prop = True

    # Class (sh:class)
    for class_uri in shapes_graph.objects(prop_shape_uri, SH.class_): # Note: SH.class_ from rdflib
        class_label = get_friendly_uri_name(shapes_graph, class_uri, ontology_graph)
        descriptions.append(format_line(constraint_detail_indent_level, f"Must be an instance of **{class_label}**."))
        constraints_found_on_prop = True

    # Value range (min/max Inclusive/Exclusive)
    range_constraints = {
        SH.minInclusive: "Must be at least **{value}**.",
        SH.maxInclusive: "Must be at most **{value}**.",
        SH.minExclusive: "Must be greater than **{value}**.",
        SH.maxExclusive: "Must be less than **{value}**.",
    }
    for pred, template in range_constraints.items():
        for val in shapes_graph.objects(prop_shape_uri, pred):
            descriptions.append(format_line(constraint_detail_indent_level, template.format(value=str(val))))
            constraints_found_on_prop = True

    # String specific (min/maxLength, pattern)
    str_constraints = {
        SH.minLength: "Must have a minimum length of **{value}**.",
        SH.maxLength: "Must have a maximum length of **{value}**.",
        SH.pattern: "Must match the pattern: '**{value}**'.",
    }
    for pred, template in str_constraints.items():
        for val_node in shapes_graph.objects(prop_shape_uri, pred): 
            msg = None
            actual_value = val_node
            if isinstance(val_node, BNode):
                for m in shapes_graph.objects(val_node, SH.message): msg = str(m)
                for v in shapes_graph.objects(val_node, RDF.value): actual_value = v
            
            flags_text = ""
            if pred == SH.pattern:
                 for f_flag in shapes_graph.objects(prop_shape_uri, SH.flags): flags_text = f" (flags: *{str(f_flag)}*)"

            if msg:
                descriptions.append(format_line(constraint_detail_indent_level, msg))
            else:
                descriptions.append(format_line(constraint_detail_indent_level, f"{template.format(value=str(actual_value))}{flags_text}"))
            constraints_found_on_prop = True


    # sh:hasValue
    for val_uri in shapes_graph.objects(prop_shape_uri, SH.hasValue):
        val_label = get_friendly_uri_name(shapes_graph, val_uri, ontology_graph)
        if isinstance(val_uri, Literal) and str(val_uri).lower() in ['true', 'false']:
            val_label = str(val_uri).lower()
        descriptions.append(format_line(constraint_detail_indent_level, f"Must be exactly **{val_label}**."))
        constraints_found_on_prop = True

    # sh:in (list of allowed values)
    for list_node in shapes_graph.objects(prop_shape_uri, SH.in_): # Note: SH.in_ from rdflib
        allowed_values = [f"**{get_friendly_uri_name(shapes_graph, item, ontology_graph)}**" for item in rdf_list_to_python_list(shapes_graph, list_node)]
        descriptions.append(format_line(constraint_detail_indent_level, f"Must be one of: {', '.join(allowed_values)}."))
        constraints_found_on_prop = True
    
    # Check if prop_shape_uri has constraints other than sh:path and basic ones already handled
    has_other_constraints_on_value = False
    for p, _ in shapes_graph.predicate_objects(prop_shape_uri):
        if p not in [SH.path, SH.message, SH.severity, SH.minCount, SH.maxCount, SH.datatype, SH.nodeKind, SH.class_,
                      SH.minInclusive, SH.maxInclusive, SH.minExclusive, SH.maxExclusive,
                      SH.minLength, SH.maxLength, SH.pattern, SH.flags, SH.hasValue, SH.in_]:
            has_other_constraints_on_value = True # e.g. sh:node, sh:and, sh:or, sh:not, sh:xone on the property value's shape
            break
    
    if has_other_constraints_on_value:
        # The "Additionally..." header is a list item, nested under the property.
        # The constraints themselves will be further nested.
        value_constraints_header_indent = constraint_detail_indent_level 
        value_constraints_list_indent = constraint_detail_indent_level + 1

        value_shape_constraints = describe_constraints_on_shape(
            shapes_graph, ontology_graph, 
            prop_shape_uri, 
            value_constraints_list_indent, # Constraints start at this deeper level
            is_property_context=True
        )
        
        if value_shape_constraints:
            descriptions.append(format_line(value_constraints_header_indent, f"**Additionally, values must satisfy:**"))
            for d_line in value_shape_constraints:
                if d_line.strip(): 
                    descriptions.append(d_line) # d_line is already formatted with its correct indent

    # Severity for the property shape
    for sev_uri in shapes_graph.objects(prop_shape_uri, SH.severity):
        sev_label = get_friendly_uri_name(shapes_graph, sev_uri, ontology_graph)
        # Add severity as a nested list item.
        # If there were other constraints, it makes sense to nest it under them.
        # If no other constraints, it's a direct attribute of the property.
        severity_text = f"Overall severity for this property: **{sev_label}**"
        if constraints_found_on_prop or has_other_constraints_on_value: # If other details exist, nest severity
             descriptions.append(format_line(constraint_detail_indent_level +1, severity_text))
        else: # Otherwise, it's a direct item under the property
             descriptions.append(format_line(constraint_detail_indent_level, severity_text))


    # If after all this, the only thing in descriptions is the property header,
    # it means this property shape (prop_shape_uri) had a sh:path but no other direct constraints here.
    # This can happen if it's just a path pointing to, for example, an sh:node that defines value constraints,
    # which would be handled by the 'has_other_constraints_on_value' block above.
    # If descriptions has more than 1 item, it means constraints were added.
    # If it's a BNode without a path, the initial call to describe_constraints_on_shape would have handled it if 'if not path_nodes:' was true.
    # No specific removal needed here, as an empty list of constraints is fine if the property truly has none directly on it beyond its path and potential sh:node.

    return descriptions


def describe_node_shape(shapes_graph, ontology_graph, node_shape_uri, indent_level=0): # indent_level is for Markdown list items
    """
    Describes a top-level NodeShape.
    """
    descriptions = []
    shape_name_friendly = get_friendly_uri_name(shapes_graph, node_shape_uri, ontology_graph)

    # Main H2 for the shape
    if not isinstance(node_shape_uri, BNode): # Named shape
        descriptions.append(format_line(0, f"## Shape: {shape_name_friendly}"))
    else: # Blank node shape
        descriptions.append(format_line(0, "## Shape (Anonymous Node)"))
    
    # Basic info items start at level 1 (top-level list items under the H2)
    current_info_indent_level = 1 

    # sh:name (often same as shape_name_friendly for named shapes, but can be different or exist for BNodes)
    for name_literal in shapes_graph.objects(node_shape_uri, SH.name):
        # Check if this is different from the main shape name already in H2
        if str(name_literal) != shape_name_friendly or isinstance(node_shape_uri, BNode):
            descriptions.append(format_line(current_info_indent_level, f"**Name**: {str(name_literal)}"))
            
    for desc_literal in shapes_graph.objects(node_shape_uri, SH.description):
        descriptions.append(format_line(current_info_indent_level, f"**Description**: {str(desc_literal)}"))
    for msg_literal in shapes_graph.objects(node_shape_uri, SH.message):
        descriptions.append(format_line(current_info_indent_level, f"**Overall Message**: {str(msg_literal)}"))

    # Targets
    target_classes = list(shapes_graph.objects(node_shape_uri, SH.targetClass))
    if target_classes:
        class_labels = [f"**{get_friendly_uri_name(shapes_graph, tc, ontology_graph)}**" for tc in target_classes]
        descriptions.append(format_line(current_info_indent_level, f"**Applies to instances of**: {', '.join(class_labels)}"))
    # Add other targets if needed, similarly formatted.

    # Custom properties
    custom_props_to_display = {
        FIREBIM.rulesource: "Rule source",
        FBB.flowchartNodeID: "Flowchart Node ID(s)"
    }
    for prop_uri, label_text in custom_props_to_display.items():
        values = list(shapes_graph.objects(node_shape_uri, prop_uri))
        if values:
            value_strs = [f"**{get_friendly_uri_name(shapes_graph, v, ontology_graph)}**" for v in values]
            descriptions.append(format_line(current_info_indent_level, f"**{label_text}**: {', '.join(value_strs)}"))
    
    # Overall Severity for the NodeShape
    for sev_uri in shapes_graph.objects(node_shape_uri, SH.severity):
        sev_label = get_friendly_uri_name(shapes_graph, sev_uri, ontology_graph)
        descriptions.append(format_line(current_info_indent_level, f"**Overall Severity**: {sev_label}"))

    # Core constraints start as list items at current_info_indent_level (effectively indent_level 1 for the list)
    # describe_constraints_on_shape will then handle further nesting.
    descriptions.extend(describe_constraints_on_shape(shapes_graph, ontology_graph, node_shape_uri, current_info_indent_level))

    return descriptions


def process_shacl_string_to_lines(shacl_data_string: str) -> list[str]:
    shapes_graph = Graph()
    ontology_graph = Graph() # Simplified: no external ontology loading for GUI

    try:
        shapes_graph.parse(data=shacl_data_string, format="turtle")
    except Exception as e:
        return [f"Error parsing SHACL input: {e}"]

    shapes_graph.bind("sh", SH)
    shapes_graph.bind("xsd", XSD)
    if FIREBIM: shapes_graph.bind("firebim", FIREBIM)
    if FBB: shapes_graph.bind("fbb", FBB)
    
    all_descriptions = []
    top_level_shapes_to_describe = set()

    for s, _, _ in shapes_graph.triples((None, SH.targetClass, None)):
        top_level_shapes_to_describe.add(s)
    for ns_uri_candidate in shapes_graph.subjects(RDF.type, SH.NodeShape):
        if isinstance(ns_uri_candidate, URIRef):
            top_level_shapes_to_describe.add(ns_uri_candidate)

    if not top_level_shapes_to_describe:
        if not set(shapes_graph.subjects(RDF.type, SH.NodeShape)):
             return ["No NodeShapes found in the SHACL input."]
        else:
             return ["No clearly top-level NodeShapes (e.g., via sh:targetClass or named NodeShapes) found. There might be component shapes defined."]

    sorted_node_shapes = sorted(list(top_level_shapes_to_describe), key=lambda x: str(x))

    for ns_uri in sorted_node_shapes:
        # format_line(0,...) ensures it's not treated as a list item by that function.
        # The leading \n is for console readability between shapes.
        all_descriptions.append(format_line(0, f"\n# NodeShape: {get_friendly_uri_name(shapes_graph, ns_uri, ontology_graph)}"))
        shape_descriptions = describe_node_shape(shapes_graph, ontology_graph, ns_uri, indent_level=0)
        all_descriptions.extend(shape_descriptions)
        all_descriptions.append("") 

    return all_descriptions

class ShaclApp:
    def __init__(self, master):
        self.master = master
        master.title("SHACL to Markdown GUI")
        master.geometry("1000x700")

        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font_family = self.default_font.actual()["family"]
        self.default_font_size = self.default_font.actual()["size"]

        self.h1_font = font.Font(family=self.default_font_family, size=int(self.default_font_size * 1.5), weight="bold")
        self.h2_font = font.Font(family=self.default_font_family, size=int(self.default_font_size * 1.2), weight="bold")
        self.bold_font = font.Font(family=self.default_font_family, size=self.default_font_size, weight="bold")
        self.normal_font = font.Font(family=self.default_font_family, size=self.default_font_size)

        self.paned_window = PanedWindow(master, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        self.input_frame = tk.Frame(self.paned_window)
        self.input_text = scrolledtext.ScrolledText(self.input_frame, wrap=tk.WORD, undo=True)
        self.input_text.pack(fill=tk.BOTH, expand=True)
        self.input_text.bind("<KeyRelease>", self.on_shacl_input_change)
        self.paned_window.add(self.input_frame, stretch="always")

        self.output_frame = tk.Frame(self.paned_window)
        self.output_text = scrolledtext.ScrolledText(self.output_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.paned_window.add(self.output_frame, stretch="always")
        
        self.output_text.tag_configure("h1", font=self.h1_font, spacing1=5, spacing3=5)
        self.output_text.tag_configure("h2", font=self.h2_font, spacing1=3, spacing3=3)
        self.output_text.tag_configure("bold", font=self.bold_font)
        self.output_text.tag_configure("normal", font=self.normal_font)
        # For error messages, could add:
        # self.output_text.tag_configure("error", foreground="red", font=self.normal_font)


    def on_shacl_input_change(self, event=None):
        shacl_content = self.input_text.get("1.0", tk.END)
        if not shacl_content.strip():
            self.clear_output()
            return
        
        markdown_lines = process_shacl_string_to_lines(shacl_content)
        self.display_markdown_in_text_widget(markdown_lines)

    def clear_output(self):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.DISABLED)

    def display_markdown_in_text_widget(self, lines):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)

        for line_content in lines:
            stripped_line_for_check = line_content.lstrip('\n') # Handle potential leading \n from H1 format

            is_h1 = False
            is_h2 = False
            text_to_parse_for_bold = line_content # Default to original line

            if stripped_line_for_check.startswith("# NodeShape:"):
                is_h1 = True
                header_text_content = stripped_line_for_check[len("# NodeShape:"):].strip()
                self.output_text.insert(tk.END, "NodeShape: " + header_text_content + "\n", "h1")
            elif stripped_line_for_check.startswith("## Shape:"):
                is_h2 = True
                header_text_content = stripped_line_for_check[len("## Shape:"):].strip()
                self.output_text.insert(tk.END, "Shape: " + header_text_content + "\n", "h2")
            elif line_content == "" and lines.index(line_content) > 0 and lines[lines.index(line_content)-1].strip() != "": # Preserve blank lines used for spacing
                self.output_text.insert(tk.END, "\n", "normal")
            elif line_content.strip() == "" and line_content != "": # line with only spaces, preserve
                self.output_text.insert(tk.END, line_content + "\n", "normal")
            elif line_content.strip(): # Non-empty, non-header line
                # Handle potential leading spaces and list marker from format_line directly
                # e.g. "  - Some text **bold**"
                # The spaces and "- " are part of line_content
                
                # Split by bold markers, preserving them for identification
                parts = re.split(r'(\*\*.*?\*\*)', line_content)
                for part in parts:
                    if part.startswith("**") and part.endswith("**"):
                        actual_text = part[2:-2]
                        self.output_text.insert(tk.END, actual_text, "bold")
                    elif part: # Non-empty part
                        self.output_text.insert(tk.END, part, "normal")
                self.output_text.insert(tk.END, "\n") # Add newline after processing all parts of the line
            # else: empty lines not matching above are skipped to avoid excessive blank lines

        self.output_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = ShaclApp(root)
    # Initial placeholder or instruction
    app.input_text.insert("1.0", "# Paste your SHACL (Turtle) content here...\n\n"
                                 "# Example:\n"
                                 "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
                                 "@prefix ex: <http://example.com/ns#> .\n"
                                 "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
                                 "ex:MyShape\n"
                                 "    a sh:NodeShape ;\n"
                                 "    sh:targetClass ex:MyClass ;\n"
                                 "    sh:property [\n"
                                 "        sh:path ex:myProperty ;\n"
                                 "        sh:datatype xsd:string ;\n"
                                 "        sh:minLength 5 ;\n"
                                 "        sh:description \"This is a test property.\" ;\n"
                                 "    ] ;\n"
                                 "    sh:property [\n"
                                 "        sh:path ex:anotherProperty ;\n"
                                 "        sh:nodeKind sh:IRI ;\n"
                                 "        sh:maxCount 1 ;\n"
                                 "    ] .\n"
    )
    app.on_shacl_input_change() # Process initial content
    root.mainloop()