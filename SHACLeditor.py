import sys
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QAction, QFileDialog,
                             QMessageBox, QSplitter, QWidget, QVBoxLayout)
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import QRegExp, QUrl, pyqtSlot, Qt, QObject
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from rdflib import Graph, URIRef, Literal, RDF, RDFS, SH
from pyshacl import validate

class TurtleHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super(TurtleHighlighter, self).__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("blue"))
        keyword_format.setFontWeight(QFont.Bold)
        keywords = ["@prefix", "@base", "a", "sh:"]
        for word in keywords:
            pattern = QRegExp("\\b" + word + "\\b")
            self.highlighting_rules.append((pattern, keyword_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("green"))
        self.highlighting_rules.append((QRegExp("\".*\""), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("red"))
        self.highlighting_rules.append((QRegExp("#[^\n]*"), comment_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)

class SHACLEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.text_edit.textChanged.connect(self.on_text_changed)

    def initUI(self):
        self.setWindowTitle("SHACL Viewer and Editor")
        self.setGeometry(100, 100, 1200, 800)

        self.splitter = QSplitter(Qt.Horizontal)
        
        # Text editor setup
        self.text_edit = QTextEdit()
        self.highlighter = TurtleHighlighter(self.text_edit.document())
        self.splitter.addWidget(self.text_edit)
        
        # Web view for visualization
        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self.onLoadFinished)
        self.splitter.addWidget(self.web_view)
        
        self.setCentralWidget(self.splitter)
        
        # Set initial sizes for splitter
        self.splitter.setSizes([600, 600])
        
        # Initialize WebChannel and Bridge
        self.web_channel = QWebChannel()
        self.bridge = Bridge(self)
        self.web_channel.registerObject('bridge', self.bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        
        self.create_menu_actions()
        
        # Load initial empty graph
        self.load_graph_data({'nodes': [], 'edges': []})

    def create_menu_actions(self):
        # Remove the Edit menu and integrate actions into a toolbar
        self.toolbar = self.addToolBar("Main Toolbar")

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        self.toolbar.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        self.toolbar.addAction(save_action)

        validate_action = QAction("Validate", self)
        validate_action.triggered.connect(self.validate)
        self.toolbar.addAction(validate_action)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open SHACL File", "", "Turtle Files (*.ttl)")
        if filename:
            with open(filename, "r") as file:
                self.text_edit.setText(file.read())
            self.update_visualization()

    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save SHACL File", "", "Turtle Files (*.ttl)")
        if filename:
            with open(filename, "w") as file:
                file.write(self.text_edit.toPlainText())

    def get_node_color(self, node_type):
        color_map = {
            str(SH.NodeShape): "#FF6B6B",  # Red
            str(SH.PropertyShape): "#4ECDC4",  # Teal
            str(RDFS.Class): "#45B7D1",  # Light Blue
            str(RDF.Property): "#FFA07A",  # Light Salmon
        }
        return color_map.get(node_type, "#C7C7C7")  # Default to light gray

    def on_text_changed(self):
        turtle_data = self.text_edit.toPlainText()
        try:
            self.rdf_graph = Graph()
            self.rdf_graph.parse(data=turtle_data, format='turtle')
            self.update_visualization()
        except Exception as e:
            pass  # Optionally handle parsing errors

    def update_visualization(self):
        g = Graph()
        turtle_data = self.text_edit.toPlainText()
        try:
            g.parse(data=turtle_data, format="turtle")
            nodes = []
            edges = []
            for s, p, o in g:
                # Determine node type and color
                s_type = next(g.objects(s, RDF.type), None)
                s_color = self.get_node_color(str(s_type) if s_type else None)
                o_type = next(g.objects(o, RDF.type), None)
                o_color = self.get_node_color(str(o_type) if o_type else None)

                nodes.append({"id": str(s), "label": str(s).split("/")[-1], "color": s_color})
                if isinstance(o, URIRef):
                    nodes.append({"id": str(o), "label": str(o).split("/")[-1], "color": o_color})
                    edges.append({"from": str(s), "to": str(o), "label": str(p).split("/")[-1]})
                elif isinstance(o, Literal):
                    # For literal values, create a node with a different shape
                    literal_id = f"{str(s)}_{str(p)}"
                    nodes.append({"id": literal_id, "label": str(o), "shape": "box", "color": "#FFFACD"})  # Light yellow
                    edges.append({"from": str(s), "to": literal_id, "label": str(p).split("/")[-1]})
            
            # Remove duplicates
            nodes = [dict(t) for t in {tuple(d.items()) for d in nodes}]
            
            self.load_graph_data({"nodes": nodes, "edges": edges})
        except Exception as e:
            QMessageBox.warning(self, "Visualization Error", f"Error visualizing SHACL: {str(e)}")

    def load_graph_data(self, graph_data):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/standalone/umd/vis-network.min.js"></script>
            <style type="text/css">
                html, body {{
                    margin: 0;
                    padding: 0;
                    width: 100%;
                    height: 100%;
                }}
                #mynetwork {{
                    width: 100%;
                    height: 100%;
                    border: 1px solid lightgray;
                }}
            </style>
        </head>
        <body>
            <div id="mynetwork"></div>
            <script type="text/javascript">
                var nodes = new vis.DataSet({json.dumps(graph_data['nodes'])});
                var edges = new vis.DataSet({json.dumps(graph_data['edges'])});
                var container = document.getElementById('mynetwork');
                var data = {{
                    nodes: nodes,
                    edges: edges
                }};
                var options = {{
                    interaction: {{
                        multiselect: true,
                        navigationButtons: true
                    }},
                    manipulation: {{
                        enabled: true,
                        addNode: function (data, callback) {{
                            var label = prompt('Enter node label:');
                            if (label !== null) {{
                                data.label = label;
                                callback(data);
                            }}
                        }},
                        editNode: function (data, callback) {{
                            var label = prompt('Edit node label:', data.label);
                            if (label !== null) {{
                                data.label = label;
                                callback(data);
                            }}
                        }},
                        addEdge: function (data, callback) {{
                            var label = prompt('Enter edge label:');
                            if (label !== null) {{
                                data.label = label;
                                callback(data);
                            }}
                        }},
                        deleteNode: true,
                        deleteEdge: true
                    }},
                    layout: {{
                        hierarchical: {{
                            enabled: true,
                            direction: 'UD',
                            sortMethod: 'directed'
                        }}
                    }},
                    nodes: {{
                        shape: 'box',
                        font: {{
                            size: 12,
                            face: 'Arial'
                        }}
                    }},
                    edges: {{
                        arrows: 'to',
                        font: {{
                            align: 'middle'
                        }}
                    }}
                }};
                var network = new vis.Network(container, data, options);

                // Bridge to communicate with PyQt
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    var pybridge = channel.objects.bridge;
                    network.on("afterDrawing", function() {{
                        pybridge.updateGraph(JSON.stringify({{
                            nodes: nodes.get(),
                            edges: edges.get()
                        }}));
                    }});
                    network.on("manipulation", function(eventType, properties) {{
                        pybridge.updateGraph(JSON.stringify({{
                            nodes: nodes.get(),
                            edges: edges.get()
                        }}));
                    }});
                }});
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content)

    @pyqtSlot(str, 'QVariantMap')
    def handle_node_update(self, event, data):
        # Here you would update the RDF graph based on the node update
        # For simplicity, we're just printing the update info
        print(f"Node updated: {data}")
        # In a real implementation, you'd update the RDF graph and the text editor content

    def onLoadFinished(self, ok):
        if ok:
            self.web_view.page().runJavaScript("""
                window.pyotherside = {
                    send: function (event, data) {
                        new QWebChannel(qt.webChannelTransport, function (channel) {
                            channel.objects.handler.handle_node_update(event, data);
                        });
                    }
                };
            """)
    
    def update_rdf_graph(self, graph_data):
        # Clear the existing graph
        self.rdf_graph = Graph()

        # Reconstruct the RDF graph from the updated visual graph data
        nodes = graph_data['nodes']
        edges = graph_data['edges']

        node_map = {}
        for node in nodes:
            node_id = URIRef(node['id'])
            node_label = Literal(node['label'])
            self.rdf_graph.add((node_id, RDF.type, SH.NodeShape))
            self.rdf_graph.add((node_id, RDFS.label, node_label))
            node_map[node['id']] = node_id

        for edge in edges:
            from_node = node_map[edge['from']]
            to_node = node_map[edge['to']]
            edge_label = URIRef(edge.get('label', 'hasProperty'))
            self.rdf_graph.add((from_node, edge_label, to_node))

        # Update the text editor with the new Turtle serialization
        turtle_data = self.rdf_graph.serialize(format='turtle')
        self.text_edit.blockSignals(True)  # Prevent recursive updates
        self.text_edit.setPlainText(turtle_data)
        self.text_edit.blockSignals(False)


    def validate(self):
        g = Graph()
        turtle_data = self.text_edit.toPlainText()
        try:
            g.parse(data=turtle_data, format="turtle")
            conforms, _, results_text = validate(g)
            if conforms:
                QMessageBox.information(self, "Validation", "SHACL validation passed.")
            else:
                QMessageBox.warning(self, "Validation", f"SHACL validation failed:\n{results_text}")
        except Exception as e:
            QMessageBox.warning(self, "Validation Error", f"Error validating SHACL: {str(e)}")

class Bridge(QObject):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor

    @pyqtSlot(str)
    def updateGraph(self, graph_json):
        graph_data = json.loads(graph_json)
        self.editor.update_rdf_graph(graph_data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = SHACLEditor()
    editor.show()
    sys.exit(app.exec_())