import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QAction, QFileDialog,
                             QMessageBox, QVBoxLayout, QWidget)
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import QRegExp
from rdflib import Graph
from pyshacl import validate
import graphviz

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

    def initUI(self):
        self.setWindowTitle("SHACL Viewer and Editor")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        layout = QVBoxLayout()
        
        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.highlighter = TurtleHighlighter(self.text_edit.document())

        self.create_menu_actions()

    def create_menu_actions(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        edit_menu = menubar.addMenu("Edit")

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        visualize_action = QAction("Visualize", self)
        visualize_action.triggered.connect(self.visualize)
        edit_menu.addAction(visualize_action)

        validate_action = QAction("Validate", self)
        validate_action.triggered.connect(self.validate)
        edit_menu.addAction(validate_action)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open SHACL File", "", "Turtle Files (*.ttl)")
        if filename:
            with open(filename, "r") as file:
                self.text_edit.setText(file.read())

    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save SHACL File", "", "Turtle Files (*.ttl)")
        if filename:
            with open(filename, "w") as file:
                file.write(self.text_edit.toPlainText())

    def visualize(self):
        g = Graph()
        turtle_data = self.text_edit.toPlainText()
        try:
            g.parse(data=turtle_data, format="turtle")
            dot = graphviz.Digraph(comment="SHACL Shapes")
            for s, p, o in g:
                dot.edge(str(s), str(o), label=str(p))
            dot.render("shacl_visualization", view=True, format="png", cleanup=True)
        except Exception as e:
            QMessageBox.warning(self, "Visualization Error", f"Error visualizing SHACL: {str(e)}")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = SHACLEditor()
    editor.show()
    sys.exit(app.exec_())