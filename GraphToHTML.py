import rdflib
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
import html
import os
import re

# Create a Graph
g = Graph()

# Parse the TTL file
g.parse("combined_document_data_graph.ttl", format="turtle")

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")

def get_text(entity):
    text = g.value(entity, FIREBIM.hasOriginalText)
    return html.escape(str(text)) if text else ""

def get_id(entity):
    id_value = g.value(entity, FIREBIM.hasID)
    return str(id_value) if id_value else ""

def process_references(entity):
    html_content = ""
    forward_refs = list(g.objects(entity, FIREBIM.hasForwardReference))
    backward_refs = list(g.objects(entity, FIREBIM.hasBackwardReference))
    
    if forward_refs or backward_refs:
        html_content += "<div class='references'>"
        for ref in forward_refs:
            ref_id = get_id(ref)
            html_content += f"<button onclick='scrollToElement(\"{ref_id}\")'>Forward to {ref_id}</button>"
        for ref in backward_refs:
            ref_id = get_id(ref)
            html_content += f"<button onclick='scrollToElement(\"{ref_id}\")'>Back to {ref_id}</button>"
        html_content += "</div>"
    
    return html_content

def clean_text(text):
    return re.sub(r'\s+', ' ', text.strip())

def process_section(section, level=1):
    section_id = get_id(section)
    section_text = get_text(section)
    html_content = f"""
    <div class='section'>
        <h{level} id='{section_id}' class='collapsible' onclick='toggleCollapse(this)'>
            {section_id} {section_text}
        </h{level}>
        <div class='content'>
    """
    
    html_content += process_references(section)
    
    # Process articles
    for article in g.objects(section, FIREBIM.hasArticle):
        html_content += process_article(article)

    # Process subsections
    for subsection in g.objects(section, FIREBIM.hasSection):
        html_content += process_section(subsection, level + 1)

    html_content += process_tables_and_figures(section)
    html_content += "</div></div>\n"
    return html_content

def process_article(article):
    article_text = get_text(article)
    html_content = f"<div class='article'>"
    
    html_content += process_references(article)
    
    # Process members and strip their text from the article text
    members = list(g.objects(article, FIREBIM.hasMember))
    member_texts = []
    for member in members:
        member_text = get_text(member)
        if member_text:
            # Check for prefixes like a), 1., b., 1), -
            match = re.match(r'^((?:\w[\).]|-)\s*)', member_text)
            if match:
                prefix = match.group(1)
                member_text = member_text[len(prefix):].strip()
            else:
                prefix = ""
            
            # Remove the member text from the article text
            clean_member_text = clean_text(member_text)
            clean_article_text = clean_text(article_text)
            if clean_member_text in clean_article_text:
                start_index = clean_article_text.index(clean_member_text)
                # Check if there's a prefix before the member text in the article
                if start_index > 0:
                    potential_prefix = article_text[start_index-2:start_index].strip()
                    if re.match(r'^(?:\w[\).]|-)\s*$', potential_prefix):
                        prefix = potential_prefix + prefix
                article_text = article_text[:start_index] + article_text[start_index + len(member_text):]
            member_texts.append((prefix, member_text))
        html_content += process_references(member)

    # Add stripped article text
    if clean_text(article_text):
        html_content += f"<p>{article_text}</p>\n"
    
    # Add member texts
    for prefix, member_text in member_texts:
        html_content += f"<div class='member'><p>{prefix}{member_text}</p></div>\n"
        html_content += process_tables_and_figures(members[member_texts.index((prefix, member_text))])

    html_content += process_tables_and_figures(article)
    html_content += "</div>\n"
    return html_content

def process_tables_and_figures(entity):
    html_content = ""
    
    # Process tables
    for table in g.objects(entity, FIREBIM.hasTable):
        table_id = get_id(table)
        table_text = get_text(table)
        html_content += process_table_or_figure(table_id, table_text, 'table')

    # Process figures
    for figure in g.objects(entity, FIREBIM.hasFigure):
        figure_id = get_id(figure)
        figure_text = get_text(figure)
        html_content += process_table_or_figure(figure_id, figure_text, 'figure')
    
    return html_content

def process_table_or_figure(item_id, item_text, item_type):
    html_content = f"<div class='{item_type}' id='{item_id}'>"
    
    # Check if image file exists
    image_path = f"{item_type}s/{item_id.replace('.', '_')}.jpg"
    if os.path.exists(image_path):
        html_content += f"<img src='{image_path}' alt='{item_type} {item_id}'>\n"
    else:
        html_content += f"<pre>{item_text}</pre>\n"
    
    html_content += f"<p>{item_type.capitalize()} {item_id}</p></div>\n"
    return html_content

# Generate HTML content
html_content = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fire Safety Regulations</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }
        h1, h2, h3, h4, h5, h6 { color: #333; cursor: pointer; }
        .article { margin-left: 20px; border-left: 2px solid #ccc; padding-left: 10px; }
        .member { margin-left: 20px; }
        .table, .figure { background-color: #f4f4f4; padding: 10px; margin: 10px 0; text-align: left; }
        .table img, .figure img { max-width: 100%; height: auto; }
        pre { white-space: pre-wrap; word-wrap: break-word; }
        .collapsible:after { content: ' ▼'; font-size: 0.7em; }
        .collapsed:after { content: ' ►'; }
        .content { display: block; }
        .collapsed + .content { display: none; }
        .references { margin-bottom: 10px; }
        .references button { margin-right: 5px; }
    </style>
    <script>
        function toggleCollapse(element) {
            element.classList.toggle('collapsed');
        }
        function scrollToElement(id) {
            const element = document.getElementById(id);
            if (element) {
                element.scrollIntoView({behavior: "smooth", block: "start"});
                // Expand all parent sections
                let parent = element.closest('.content');
                while (parent) {
                    const header = parent.previousElementSibling;
                    if (header && header.classList.contains('collapsible')) {
                        header.classList.remove('collapsed');
                    }
                    parent = parent.parentElement.closest('.content');
                }
            }
        }
    </script>
</head>
<body>
    <h1>Fire Safety Regulations</h1>
"""

# Process top-level sections
document = URIRef(FIREBIM.RoyalDecree)
for section in g.objects(document, FIREBIM.hasSection):
    html_content += process_section(section)

html_content += """
</body>
</html>
"""

# Write the HTML content to a file
with open("fire_safety_regulations.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML file 'fire_safety_regulations.html' has been generated.")