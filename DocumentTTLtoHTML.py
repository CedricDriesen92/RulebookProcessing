from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.plugins.sparql import prepareQuery
import html
import rdflib
import os
import re
import urllib.parse

# Define namespaces
FIREBIM = Namespace("http://example.com/firebim#")
rdf = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
sh = Namespace("http://www.w3.org/ns/shacl#")

# Create a Graph
g = Graph()

# Parse the TTL file
filename = "VejledningDK"
g.parse("documentgraphs/"+filename+".pdf/combined_document_data_graph.ttl", format="turtle")


def load_all_shapes(directory):
    shapes = {}
    shapes_graph = Graph()
    for filename in os.listdir(directory):
        if filename.endswith(".ttl"):
            print(f"Loading shape file: {filename}")
            graph = rdflib.Graph()
            graph.parse(os.path.join(directory, filename), format="turtle")
            for shape in graph.subjects(rdf.type, sh.NodeShape):
                shape_id = shape.split('#')[-1]
                shapes[shape_id] = graph.serialize(format='turtle')
            shapes_graph += graph
    
    print("Namespaces in shapes graph:")
    for prefix, namespace in shapes_graph.namespaces():
        print(f"{prefix}: {namespace}")
    
    print("\nTotal triples in shapes graph:", len(shapes_graph))
    
    return shapes, shapes_graph

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

def process_section(section, level=1):
    section_id = get_id(section)
    section_text = get_text(section)
    
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
    
    # Process articles
    for article in g.objects(section, FIREBIM.hasArticle):
        html_content += process_article(article)

    # Process subsections
    for subsection in g.objects(section, FIREBIM.hasSection):
        html_content += process_section(subsection, level + 1)

    html_content += process_tables_and_figures(section)
    html_content += process_references(section)
    html_content += "</div></div>\n"
    return html_content

def process_article(article):
    article_text = normalize_text(get_text(article))
    article_id = get_id(article)
    html_content = f"<div class='article' id='{article_id}'>"
    
    html_content += f"""
    <div class="article-content">
        <span style="font-size: 16px; color: grey" class="subtle-id">Article {article_id}</span>
    </div>
    <div class="original-text" style="display:block;">
        <p>{article_text}</p>
    """
    
    # Process top-level members
    top_level_members = list(g.objects(article, FIREBIM.hasMember))
    html_content += process_members(top_level_members)

    # Process tables and figures
    html_content += process_tables_and_figures(article)
    html_content += process_references(article)
    html_content += "</div></div>\n"
    return html_content

def process_members(members, level=0):
    html_content = ""
    sorted_members = sort_members(members)
    
    # Prepare the SPARQL query
    query = prepareQuery("""
        SELECT ?shape
        WHERE {
            ?member <http://example.org/firebim#hasRelatedShape> ?shape .
        }
    """)
    
    for member in sorted_members:
        member_id = get_uri_id(member)
        member_text = normalize_text(get_text(member))
        
        html_content += f"""
        <div class='member level-{level}' id='member-{member_id.replace(".", "-")}'>
            <span style="font-size: 10px; color: grey" class="subtle-id">Member {member_id}</span>
            <p>{member_text}</p>
        """
        
        # Add button for showing related shape
        member_uri = URIRef(f"http://example.org/firebim#Member_{member_id.replace('.', '_')}")
        #print(f"Searching for related shapes with member URI: {member_uri}")
        
        # Use SPARQL query to find related shapes
        results = shapes_graph.query(query, initBindings={'member': member_uri})
        related_shapes = [row.shape for row in results]
        
        #print(f"Found related shapes: {related_shapes}")
        if related_shapes:
            shape_id = related_shapes[0].split('#')[-1]  # Extract the shape ID from the URI
            if shape_id in shapes:
                html_content += f"""
                <button class='show-shape-button' onclick='showShape("{shape_id}")'>Show Related Shape</button>
                """
            print(f"Related shapes found: {member_id} -> {shape_id}")
        #else:
        #    print(f"No related shapes found for member: {member_id}")
        
        # Process nested members
        nested_members = list(g.objects(member, FIREBIM.hasMember))
        if nested_members:
            html_content += process_members(nested_members, level + 1)
        
        html_content += process_references(member)
        html_content += "</div>"
    
    return html_content

def sort_members(members):
    def get_sort_key(member):
        member_id = get_uri_id(member)
        return tuple(int(part) for part in member_id.split('.') if part.isdigit())
    
    return sorted(members, key=get_sort_key)

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

def generate_table_of_contents(g, document):
    toc_html = "<h2>Table of Contents</h2><ul>"
    for section in g.objects(document, FIREBIM.hasSection):
        if get_id(section).count('.') == 0:
            toc_html += process_toc_section(g, section, 1)
    toc_html += "</ul>"
    return toc_html

def process_toc_section(g, section, level):
    section_id = get_id(section)
    section_text = get_text(section)
    if level < 3:
        html = f"<li><a href='#{section_id}' onclick='scrollToElement(\"{section_id}\"); return false;'>{section_id} {section_text}</a>"
    else:
        html = f"<li><a href='#{section_id}' onclick='scrollToElement(\"{section_id}\"); return false;'>{section_id}</a>"
    
    if level < 2:  # Only process subsections for the first two levels
        subsections = list(g.objects(section, FIREBIM.hasSection))
        if subsections:
            html += "<ul>"
            for subsection in subsections:
                html += process_toc_section(g, subsection, level + 1)
            html += "</ul>"
    
    html += "</li>"
    return html


# Load all shapes
shapes, shapes_graph = load_all_shapes("shacl_shapes_mmd")

# Generate HTML content
html_content = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document graph</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #C5C5C5;
        }
        #sidebar {
            width: 250px;
            height: 100vh;
            overflow-y: auto;
            background-color: #f0f0f0;
            padding: 20px;
            position: fixed;
            left: 0;
            top: 0;
            box-shadow: 2px 0 5px rgba(0,0,0,0.1);
        }
        #main-content {
            top: 25px;
            right: 25px;
            bottom: 25px;
            margin-left: 290px;
            padding: 20px;
            max-width: 9999px;
        }
        .section {
            background-color: #ffffff;
            border-radius: 8px;
            margin-bottom: 10px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .section .section {
            background-color: #e6f2ff;
        }
        .section .section .section {
            background-color: #fff9e6;
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
            left: 10px;
            line-height: 0.5;
        }
        .member p {
            margin-top: 0;
            padding-top: 0em;
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
        highlight-toc {
            background-color: #ffe6b3;
            font-weight: bold;
        }
        .highlight {
            background-color: yellow;
            font-weight: bold;
        }
        .shape-modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.4);
            overflow: auto;
        }

        .shape-modal-content {
            background-color: #fefefe;
            margin: 5% auto;
            padding: 20px;
            border: 1px solid #888;
            width: 80%;
            max-width: 800px;
            max-height: 80vh;
            overflow-y: auto;
        }

        .shape-modal-content pre {
            white-space: pre-wrap;
            word-wrap: break-word;
            max-width: 100%;
            overflow-x: auto;
        }

        .close-modal {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }

        .close-modal:hover,
        .close-modal:focus {
            color: black;
            text-decoration: none;
            cursor: pointer;
        }

        .show-shape-button {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 5px 10px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 12px;
            margin: 4px 2px;
            cursor: pointer;
            border-radius: 4px;
        }
        #id-toggle-container {
            position: fixed;
            top: 10px;
            right: 10px;
            background-color: #fff;
            padding: 5px 10px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            z-index: 1000;
        }
        #search-container {
            position: sticky;
            top: 0;
            background-color: #fff;
            padding: 0px;
            margin-bottom: 0px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            z-index: 1000;
        }
        #search-input {
            width: 100%;
            padding: 0px;
            font-size: 16px;
        }
        #search-results {
            margin-top: 10px;
            font-size: 14px;
        }
        .highlight {
            background-color: yellow;
        }
        #sidebar ul {
            list-style-type: none;
            padding-left: 20px;
        }
        #sidebar > ul {
            padding-left: 0;
        }
        #sidebar li {
            margin-bottom: 5px;
        }
        #sidebar a {
            text-decoration: none;
            color: #333;
        }
        #sidebar a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div id="sidebar">
        <div id="search-container">
            <input type="text" id="search-input" placeholder="Search...">
            <div id="search-results"></div>
        </div>
        <div>
            table_of_contents_location
        </div>
    </div>
    <div id="main-content">
        <div id="id-toggle-container">
            <label for="id-toggle">
                <input type="checkbox" id="id-toggle" onchange="toggleIDs()"> Show IDs
            </label>
        </div>
        <h1 style="color: black;">Koninklijk Besluit Brandveiligheid</h1>
"""

# Process top-level sections
document = URIRef(FIREBIM.RoyalDecree)
for section in g.objects(document, FIREBIM.hasSection):
    if get_id(section).count('.') == 0:
        html_content += process_section(section)

html_content += """
    <script>

    const shapes = {
"""

for shape_id, shape_content in shapes.items():
    html_content += f"'{shape_id}': `{shape_content}`,\n"

html_content += """
    };

    function showShape(shapeId) {
        const shapeContent = shapes[shapeId];
        if (shapeContent) {
            const modal = document.createElement('div');
            modal.className = 'shape-modal';
            modal.style.display = 'block';
            modal.innerHTML = `
                <div class="shape-modal-content">
                    <span class="close-modal">&times;</span>
                    <h2>Shape: ${shapeId}</h2>
                    <pre>${escapeHtml(shapeContent)}</pre>
                </div>
            `;
            document.body.appendChild(modal);

            const closeButton = modal.querySelector('.close-modal');
            closeButton.onclick = function() {
                document.body.removeChild(modal);
            }

            window.onclick = function(event) {
                if (event.target == modal) {
                    document.body.removeChild(modal);
                }
            }
        } else {
            console.error(`Shape with id ${shapeId} not found`);
        }
    }

    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

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
            subtleIDs[i].style.display = checkbox.checked ? 'inline' : 'none';
        }
    }
    toggleIDs();
    
    // Search functionality
    let searchResults = [];
    let currentResultIndex = -1;

    function resetSearchState() {
        searchResults = [];
        currentResultIndex = -1;
        clearHighlights();
        document.getElementById('search-results').innerHTML = '';
    }

    function performSearch() {
        resetSearchState();
        
        const searchTerm = document.getElementById('search-input').value.toLowerCase();
        console.log(`Performing search for: "${searchTerm}"`);
        
        if (searchTerm.length < 2) {
            return;
        }
        
        const mainContent = document.getElementById('main-content');
        searchInNode(mainContent, searchTerm);
        
        console.log(`Found ${searchResults.length} results`);
        
        if (searchResults.length > 0) {
            highlightResults();
            highlightTableOfContents();
            updateSearchResults();
        } else {
            updateSearchResults();
        }
    }

    function searchInNode(node, searchTerm) {
        if (node.nodeType === Node.TEXT_NODE) {
            const parent = node.parentElement;
            if (parent && isVisible(parent)) {
                const text = node.textContent.toLowerCase();
                let index = text.indexOf(searchTerm);
                while (index !== -1) {
                    // Store the parent element instead of the text node
                    searchResults.push({
                        element: parent,
                        textContent: node.textContent,
                        index: index,
                        length: searchTerm.length
                    });
                    index = text.indexOf(searchTerm, index + 1);
                }
            }
        } else if (node.nodeType === Node.ELEMENT_NODE && node.nodeName !== 'SCRIPT') {
            if (isVisible(node)) {
                for (let child of node.childNodes) {
                    searchInNode(child, searchTerm);
                }
            }
        }
    }

    function clearHighlights() {
        const highlights = document.getElementsByClassName('highlight');
        while (highlights.length > 0) {
            const parent = highlights[0].parentNode;
            parent.replaceChild(document.createTextNode(highlights[0].textContent), highlights[0]);
            parent.normalize();
        }
        
        const highlightedSections = document.getElementsByClassName('highlight-section');
        while (highlightedSections.length > 0) {
            highlightedSections[0].classList.remove('highlight-section');
        }
        
        const tocHighlights = document.querySelectorAll('#sidebar .highlight-toc');
        console.log(`Found ${tocHighlights.length} TOC highlights to clear`);
    }

    function highlightResults() {
        searchResults.forEach((result, index) => {
            try {
                highlightNode(result);
                
                // Highlight the containing section
                let section = findAncestorByClass(result.element, 'section');
                if (section) {
                    section.classList.add('highlight-section');
                }
            } catch (e) {
                console.error(`Error highlighting result ${index + 1}:`, e);
            }
        });
    }

    function highlightNode(result) {
        const element = result.element;
        const text = result.textContent;
        const index = result.index;
        const length = result.length;

        const beforeText = text.slice(0, index);
        const highlightedText = text.slice(index, index + length);
        const afterText = text.slice(index + length);

        const span = document.createElement('span');
        span.className = 'highlight';
        span.textContent = highlightedText;

        const fragment = document.createDocumentFragment();
        fragment.appendChild(document.createTextNode(beforeText));
        fragment.appendChild(span);
        fragment.appendChild(document.createTextNode(afterText));

        // Replace all child nodes with our new fragment
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
        element.appendChild(fragment);
    }

    function updateSearchResultsDisplay() {
        const resultsContainer = document.getElementById('search-results');
        if (searchResults.length > 0) {
            resultsContainer.innerHTML = `Showing result ${currentResultIndex + 1} of ${searchResults.length}. Press Enter for next.`;
        } else {
            resultsContainer.innerHTML = 'No results found.';
        }
    }

    function updateSearchResults() {
        const resultsContainer = document.getElementById('search-results');
        if (searchResults.length > 0) {
            resultsContainer.innerHTML = `Found ${searchResults.length} results. Press Enter to navigate.`;
        } else {
            resultsContainer.innerHTML = 'No results found.';
        }
    }

    function isVisible(element) {
        const isVis = !!(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
        console.log(`Visibility check for ${element.tagName}: ${isVis}`);
        return isVis;
    }

    function findAncestorByClass(element, className) {
        while (element) {
            if (element.classList && element.classList.contains(className)) {
                return element;
            }
            element = element.parentElement;
        }
        return null;
    }
    
    function highlightTableOfContents() {
        console.log("Highlighting table of contents");
        const toc = document.getElementById('sidebar');
        const highlightedSections = document.getElementsByClassName('highlight-section');
        
        // First, remove all existing highlight-toc classes
        const existingHighlights = toc.querySelectorAll('.highlight-toc');
        existingHighlights.forEach(el => el.classList.remove('highlight-toc'));
        
        for (let section of highlightedSections) {
            let currentElement = section;
            while (currentElement && currentElement.id) {
                const sectionId = currentElement.id;
                const tocEntry = toc.querySelector(`a[href="#${sectionId}"]`);
                if (tocEntry) {
                    tocEntry.classList.add('highlight-toc');
                    // Expand parent lists to make highlighted item visible
                    let parent = tocEntry.closest('ul');
                    while (parent && parent !== toc) {
                        parent.style.display = 'block';
                        parent = parent.parentElement.closest('ul');
                    }
                }
                currentElement = currentElement.parentElement;
            }
        }
    }
    
    function findHighlightElement(node) {
        if (!node) {
            console.error("Node is null in findHighlightElement");
            return null;
        }
        if (node.nodeType === Node.TEXT_NODE) {
            return node.parentElement ? node.parentElement.querySelector('.highlight') : null;
        }
        return node.querySelector('.highlight');
    }
    
    function findScrollableParent(node) {
        if (!node) return document.body;
        
        // If node is a text node, start from its parent
        if (node.nodeType === Node.TEXT_NODE) {
            node = node.parentElement;
        }
        
        if (!node || node === document.body) return document.body;
        
        const overflowY = window.getComputedStyle(node).overflowY;
        if (overflowY === 'auto' || overflowY === 'scroll') return node;
        
        return findScrollableParent(node.parentElement);
    }

    function getNodePosition(node) {
        if (!node) return null;
        
        // If node is a text node, use its parent for getting the position
        const element = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        if (!element) return null;
        
        const rect = element.getBoundingClientRect();
        return {
            top: rect.top + window.pageYOffset,
            left: rect.left + window.pageXOffset
        };
    }

    function goToNextResult() {
        if (searchResults.length === 0) {
            console.log("No search results.");
            return;
        }
        
        currentResultIndex = (currentResultIndex + 1) % searchResults.length;
        const result = searchResults[currentResultIndex];
        
        if (result && result.element) {
            const scrollableParent = findScrollableParent(result.element);
            const nodePosition = getNodePosition(result.element);
            
            if (nodePosition) {
                if (scrollableParent === document.body) {
                    window.scrollTo({
                        top: nodePosition.top - 100,
                        behavior: 'smooth'
                    });
                } else {
                    scrollableParent.scrollTo({
                        top: nodePosition.top - scrollableParent.getBoundingClientRect().top - 100,
                        behavior: 'smooth'
                    });
                }
                
                console.log(`Scrolled to result ${currentResultIndex + 1}`);
                
                // Temporarily highlight the result
                const highlightElement = result.element;
                if (highlightElement) {
                    const originalBackground = highlightElement.style.backgroundColor;
                    highlightElement.style.backgroundColor = 'yellow';
                    setTimeout(() => {
                        highlightElement.style.backgroundColor = originalBackground;
                    }, 1000);
                }
            } else {
                console.error("Could not determine position for result", result);
            }
        } else {
            console.error("Invalid result at index", currentResultIndex);
        }
        
        updateSearchResultsDisplay();
    }
    
    // Event listeners
    document.getElementById('search-input').addEventListener('input', performSearch);
    document.getElementById('search-input').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && searchResults.length > 0) {
            goToNextResult();
        }
    });
</script>
</body>
</html>
"""

# Create ToC
table_of_contents = generate_table_of_contents(g, document)
html_content = html_content.replace('table_of_contents_location', table_of_contents)
# Write the HTML content to a file
with open(filename+".html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML file '"+filename+".html' has been generated.")