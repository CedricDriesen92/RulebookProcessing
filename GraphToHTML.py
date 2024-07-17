import difflib
import rdflib
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS
import html
import os
import re
import urllib.parse

# Create a Graph
g = Graph()

# Parse the TTL file
g.parse("combined_document_data_graph.ttl", format="turtle")

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")

def fuzzy_find(text, pattern, threshold=0.85):
    for i in range(len(text)):
        for j in range(i + 1, len(text) + 1):
            substring = text[i:j]
            if len(substring) > 3 and difflib.SequenceMatcher(None, substring, pattern).ratio() > threshold:
                return i, j
    return -1, -1

def normalize_text(text):
    # Remove language tags and normalize whitespace
    text = re.sub(r'@\w+$', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def get_text(entity):
    text = g.value(entity, FIREBIM.hasOriginalText)
    return html.escape(str(text)) if text else ""

def get_id(entity):
    id_value = g.value(entity, FIREBIM.hasID)
    return str(id_value) if id_value else ""

def get_uri_id(entity):
    id_value = g.value(entity, FIREBIM.hasID)
    if id_value:
        return str(id_value)
    else:
        # Extract ID from URI for members
        uri = str(entity)
        match = re.search(r'Member_(.+)$', uri)
        if match:
            return match.group(1).replace('_', '.')
    return ""

def clean_text(text):
    return re.sub(r'\s+', ' ', text.strip())

def process_section(section, level=1):
    section_id = get_id(section)
    section_text = get_text(section)
    
    # Check if it's a subsubsection (two or more dots in the ID)
    is_subsubsection = section_id.count('.') >= 2
    
    if is_subsubsection:
        html_content = f"""
        <div class='subsubsection' id='{section_id}'>
            <p><strong>{section_id}</strong> {section_text}</p>
            <div class='subsubsection-content'>
        """
    else:
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
    article_text = normalize_text(get_text(article))
    article_id = get_id(article)
    html_content = f"<div class='article' id='{article_id}'>"
    
    html_content += f"""
    <div class="toggle-button">
        <button onclick="toggleOriginalText(this)">Show Original</button>
    </div>
    <div class="original-text" style="display:none;">
        <p>{article_text}</p>
    </div>
    <div class="article-content">
        <span style="font-size: 26 px; color: grey" class="subtle-id">Article {article_id}</span>
    """
    
    # Process references
    html_content += process_references(article)
    
    # Process members
    members = list(g.objects(article, FIREBIM.hasMember))
    member_texts = []
    for member in members:
        html_content += process_references(member)
        member_text = normalize_text(get_text(member))
        if member_text:
            member_texts.append((member, member_text))

    # Sort member_texts by their position in the article_text
    member_texts.sort(key=lambda x: article_text.index(x[1]) if x[1] in article_text else len(article_text))

    # Process article text
    remaining_text = article_text
    processed_members = []
    remaining_text_post = []
    if len(members) > 1:
        for member, member_text in member_texts:
            if member_text in remaining_text:
                parts = remaining_text.split(member_text, 1)
                processed_members.append((member, member_text))
                remaining_text = parts[1]
                remaining_text_post.append(parts[0])
            else:
                processed_members.append((member, member_text))

        # Add member texts
        for i, (member, member_text) in enumerate(processed_members):
            html_content += f"<p>{remaining_text_post[i]}</p>\n"
            html_content += process_member(member, member_text)
        try:
            html_content += f"<p>{remaining_text_post[-1]}</p>\n"
        except:
            print("nothing left")
    else:
        html_content += process_member(members[0], member_texts[0][1])

    # Process tables and figures
    html_content += process_tables_and_figures(article)

    html_content += "</div></div>\n"
    return html_content

def process_member(member, member_text):
    member_id = get_uri_id(member)
    return f"""
    <div class='member'>
        <span style="font-size: 10px; color: grey"class="subtle-id">Member {member_id}</span>
        <p>{member_text}</p>
    </div>
    """

def process_references(entity):
    html_content = ""
    forward_refs = list(g.objects(entity, FIREBIM.hasForwardReference))
    backward_refs = list(g.objects(entity, FIREBIM.hasBackwardReference))
    external_refs = list(g.objects(entity, FIREBIM.hasReference))
    
    if forward_refs or backward_refs or external_refs:
        html_content += "<div class='references'>"
        for ref in forward_refs:
            ref_id = get_id(ref)
            html_content += f"<button class='reference-button' onclick='scrollToElement(\"{ref_id}\")'>→ {ref_id}</button>"
        for ref in backward_refs:
            ref_id = get_id(ref)
            html_content += f"<button class='reference-button' onclick='scrollToElement(\"{ref_id}\")'>← {ref_id}</button>"
        for ref in external_refs:
            ref_id = get_id(ref)
            encoded_ref = urllib.parse.quote(ref_id)
            html_content += f"<a href='https://www.google.com/search?q={encoded_ref}' target='_blank' class='reference-button external'>☆ {ref_id}</a>"
        html_content += "</div>"
    
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
    <title>Koninklijk Besluit Brandveiligheid</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 10px;
            background-color: #f5f5f5;
        }
        .section {
            background-color: #ffffff;
            border-radius: 8px;
            margin-bottom: 10px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .article {
            background-color: #ffffff;
            border-radius: 8px;
            margin-bottom: 8px;
            padding: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            position: relative;
        }
        .article-content {
            margin-top: 5px;
        }
        .toggle-button {
            position: absolute;
            bottom: 5px;
            right: 5px;
        }
        .toggle-button button {
            background-color: transparent;
            border: none;
            color: #007bff;
            font-size: 0.8em;
            cursor: pointer;
            transition: color 0.3s;
        }
        .toggle-button button:hover {
            color: #0056b3;
        }
        .member {
            margin-left: 20px;
            border-left: 2px solid #e0e0e0;
            padding-left: 10px;
            margin-top: 8px;
        }
        
        .member .subtle-id {
            font-size: 0.7em;
            color: #999;
            font-weight: normal;
            top: 4;
            left: 10px; /* Adjust as needed */
            line-height: 0.5; /* Ensure it doesn't add extra space */
        }
        .member p {
            margin-top: 0; /* Remove top margin */
            padding-top: 0em; /* Add padding to make room for the ID */
            margin-bottom: 2px;
        }
        .references {
            margin-bottom: 15px;
            font-size: 0.9em;
        }
        .reference-button {
            background-color: #e9ecef;
            border: none;
            border-radius: 4px;
            padding: 3px 4px;
            font-size: 0.8em;
            cursor: pointer;
            margin-top: 5px;
            transition: background-color 0.3s;
            color: #495057;
            text-decoration: none;
            display: inline-block;
            margin-right: 5px;
        }
        .reference-button:hover {
            background-color: #ced4da;
        }
        .reference-button.external {
            background-color: #d4edda;
            color: #155724;
        }
        .reference-button.external:hover {
            background-color: #c3e6cb;
        }
        .table, .figure {
            margin: 15px 0;
            border-radius: 4px;
            overflow: hidden;
        }
        .table img, .figure img {
            max-width: 100%;
            height: auto;
            display: block;
        }
        .subsubsection {
            background-color: #f9f9f9;
            border-left: 3px solid #999999;
            padding: 8px;
            margin-bottom: 10px;
        }
        .subsubsection p {
            margin: 0;
            font-size: 1em;
        }
        .subsubsection-content {
            margin-top: 10px;
        }
        .collapsible {
            cursor: pointer;
        }
        .collapsible:after {
            content: ' ▼';
            font-size: 0.7em;
            vertical-align: middle;
        }
        .collapsed:after {
            content: ' ►';
        }
        .content {
            display: block;
        }
        .collapsed + .content {
            display: none;
        }
        .subtle-id {
            font-weight: normal;
            margin-right: 5px;
            vertical-align: super;
        }
        
        #id-toggle-container {
            position: fixed;
            top: 10px;
            right: 10px;
            background-color: #fff;
            padding: 5px 10px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
    </style>
    <script>
        function toggleOriginalText(button) {
            var originalText = button.parentElement.nextElementSibling;
            if (originalText.style.display === "none") {
                originalText.style.display = "block";
                button.textContent = "Hide Original";
            } else {
                originalText.style.display = "none";
                button.textContent = "Show Original";
            }
        }
        function scrollToElement(id) {
            const element = document.getElementById(id);
            if (element) {
                element.scrollIntoView({behavior: "smooth", block: "start"});
                element.style.backgroundColor = "#e6f2ff";
                setTimeout(() => {
                    element.style.transition = "background-color 1s ease";
                    element.style.backgroundColor = "";
                }, 50);
            }
        }
        function toggleCollapse(element) {
            element.classList.toggle('collapsed');
            var content = element.nextElementSibling;
            if (content.style.display === "block" || content.style.display === "") {
                content.style.display = "none";
            } else {
                content.style.display = "block";
            }
        }
        function toggleIDs() {
            var checkbox = document.getElementById('id-toggle');
            var subtleIDs = document.getElementsByClassName('subtle-id');
            for (var i = 0; i < subtleIDs.length; i++) {
                subtleIDs[i].style.display = checkbox.checked ? 'none' : 'inline';
            }
        }
    </script>
</head>
<body>
    <div id="id-toggle-container">
        <label for="id-toggle">
            <input type="checkbox" id="id-toggle" onchange="toggleIDs()"> Hide IDs
        </label>
    </div>
    <h1>Koninklijk Besluit Brandveiligheid</h1>
"""

# Process top-level sections
document = URIRef(FIREBIM.RoyalDecree)
for section in g.objects(document, FIREBIM.hasSection):
    if get_id(section).count('.') == 0:
        html_content += process_section(section)

html_content += """
</body>
</html>
"""

# Write the HTML content to a file
with open("fire_safety_regulations.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML file 'fire_safety_regulations.html' has been generated.")