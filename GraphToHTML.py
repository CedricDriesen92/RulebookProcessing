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
    html_content += process_references(section)  # Moved to the end
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
    
    # Process members
    members = list(g.objects(article, FIREBIM.hasMember))
    member_texts = []
    for member in members:
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
    html_content += process_references(article)  # Moved to the end
    html_content += "</div></div>\n"
    return html_content

def process_member(member, member_text):
    member_id = get_uri_id(member)
    html_content = f"""
    <div class='member'>
        <span style="font-size: 10px; color: grey"class="subtle-id">Member {member_id}</span>
        <p>{member_text}</p>
    """
    html_content += process_references(member)  # Added references processing
    html_content += "</div>"
    return html_content

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
                <input type="checkbox" id="id-toggle" onchange="toggleIDs()"> Hide IDs
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
                    console.log(`Found match in node: "${node.textContent.slice(index, index + searchTerm.length)}"`);
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
        console.log("Clearing existing highlights");
        const highlights = document.getElementsByClassName('highlight');
        console.log(`Found ${highlights.length} highlights to clear`);
        while (highlights.length > 0) {
            const parent = highlights[0].parentNode;
            parent.replaceChild(document.createTextNode(highlights[0].textContent), highlights[0]);
            parent.normalize();
        }
        
        const highlightedSections = document.getElementsByClassName('highlight-section');
        console.log(`Found ${highlightedSections.length} highlighted sections to clear`);
        while (highlightedSections.length > 0) {
            highlightedSections[0].classList.remove('highlight-section');
        }
        
        const tocHighlights = document.querySelectorAll('#sidebar .highlight-toc');
        console.log(`Found ${tocHighlights.length} TOC highlights to clear`);
        tocHighlights.forEach(el => el.classList.remove('highlight-toc'));
    }

    function highlightResults() {
        console.log(`Highlighting ${searchResults.length} results`);
        searchResults.forEach((result, index) => {
            try {
                console.log(`Highlighting result ${index + 1}: "${result.textContent.slice(result.index, result.index + result.length)}"`);
                highlightNode(result);
                
                // Highlight the containing section
                let section = findAncestorByClass(result.element, 'section');
                if (section) {
                    console.log(`Highlighting section: ${section.id}`);
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
        console.log(`Removing ${existingHighlights.length} existing TOC highlights`);
        existingHighlights.forEach(el => el.classList.remove('highlight-toc'));
        
        console.log(`Found ${highlightedSections.length} highlighted sections to process for TOC`);
        for (let section of highlightedSections) {
            let currentElement = section;
            while (currentElement && currentElement.id) {
                const sectionId = currentElement.id;
                const tocEntry = toc.querySelector(`a[href="#${sectionId}"]`);
                if (tocEntry) {
                    console.log(`Highlighting TOC entry for section: ${sectionId}`);
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
            console.log("No search results to navigate");
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
table_of_contents = generate_table_of_contents(g, document)
html_content = html_content.replace('table_of_contents_location', table_of_contents)
# Write the HTML content to a file
with open("fire_safety_regulations.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML file 'fire_safety_regulations.html' has been generated.")