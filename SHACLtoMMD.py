#!/usr/bin/env python3
"""
SHACLtoMMD.py - Convert SHACL Turtle files to Mermaid diagrams with visualization.

Parses SHACL shapes from .ttl files and generates:
  - Individual .mmd (Mermaid) files per shape
  - A combined HTML file with interactive Mermaid.js visualization

Usage:
    python SHACLtoMMD.py <input_path> [--output-dir <dir>]

    input_path: A .ttl file or directory containing .ttl files

Handles all SHACL constraint patterns:
    sh:or, sh:and, sh:not, sh:property, sh:node, sh:sparql,
    sh:qualifiedValueShape, sh:inversePath, sh:targetClass,
    sh:SPARQLTarget, sh:PropertyShape, nested blank nodes, etc.
"""

import os
import sys
import argparse
import glob
import html as html_mod
from rdflib import Graph, Namespace, URIRef, BNode, Literal, RDF
from rdflib.collection import Collection

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
SH = Namespace("http://www.w3.org/ns/shacl#")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_LABEL_LEN = 120
MAX_MSG_LEN = 80
MAX_DEPTH = 15


# ===================================================================
# Core converter
# ===================================================================
class SHACLtoMermaid:
    """Converts SHACL shapes from an rdflib Graph into Mermaid flowchart syntax."""

    def __init__(self, graph: Graph):
        self.g = graph
        self._counter = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _nid(self, prefix: str = "N") -> str:
        """Generate a unique Mermaid node id."""
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _qn(self, node) -> str:
        """Shortened prefixed name for a URI / literal / blank node."""
        if isinstance(node, BNode):
            return f"_:{node}"
        if isinstance(node, Literal):
            return str(node)
        try:
            return self.g.namespace_manager.qname(node)
        except Exception:
            s = str(node)
            return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]

    @staticmethod
    def _esc(text: str, maxlen: int = MAX_LABEL_LEN) -> str:
        """Escape / sanitise text for safe inclusion inside Mermaid labels."""
        t = str(text)
        for old, new in [
            ('"', "'"),
            ("\n", " "),
            ("\r", ""),
            ("#", ""),
            ("`", "'"),
            ("&", " and "),
        ]:
            t = t.replace(old, new)
        t = t.strip()
        return (t[: maxlen - 3] + "...") if len(t) > maxlen else t

    def _path_label(self, node) -> str:
        """Human-readable label for a property path (incl. inverse paths)."""
        if isinstance(node, BNode):
            for inv in self.g.objects(node, SH.inversePath):
                return f"^{self._qn(inv)}"
        return self._qn(node)

    def _rdf_list(self, head) -> list:
        """Collect items from an RDF collection (rdf:first/rdf:rest chain)."""
        try:
            return list(Collection(self.g, head))
        except Exception:
            return []

    def _msg(self, node) -> str | None:
        """Return the first sh:message on *node*, or None."""
        for m in self.g.objects(node, SH.message):
            return str(m)
        return None

    # ------------------------------------------------------------------
    # Property-shape label builder (scalar constraints only)
    # ------------------------------------------------------------------
    def _prop_label(self, pnode) -> str:
        """Build a concise text label for a property constraint.

        Only scalar / direct attributes are included here; nested
        structural constraints (sh:or, sh:and, sh:node, sub-properties)
        are rendered as visual branches by ``_build()``.
        """
        parts: list[str] = []

        # path
        for p in self.g.objects(pnode, SH.path):
            parts.append(self._path_label(p))

        # class
        for c in self.g.objects(pnode, SH["class"]):
            parts.append(f"class: {self._qn(c)}")

        # hasValue
        for v in self.g.objects(pnode, SH.hasValue):
            parts.append(f"= {v}")

        # datatype
        for dt in self.g.objects(pnode, SH.datatype):
            parts.append(self._qn(dt))

        # numeric range constraints
        for pred, sym in [
            (SH.minInclusive, ">="),
            (SH.maxInclusive, "<="),
            (SH.minExclusive, ">"),
            (SH.maxExclusive, "<"),
        ]:
            for v in self.g.objects(pnode, pred):
                parts.append(f"{sym} {v}")

        # cardinality
        for v in self.g.objects(pnode, SH.minCount):
            parts.append(f"min: {v}")
        for v in self.g.objects(pnode, SH.maxCount):
            parts.append(f"max: {v}")

        # qualified value shape (simplified — just the class)
        for qvs in self.g.objects(pnode, SH.qualifiedValueShape):
            for c in self.g.objects(qvs, SH["class"]):
                parts.append(f"qualifies: {self._qn(c)}")
        for v in self.g.objects(pnode, SH.qualifiedMinCount):
            parts.append(f"qmin: {v}")

        # sh:in value list
        for il in self.g.objects(pnode, SH["in"]):
            items = self._rdf_list(il)
            vals = ", ".join(str(i) for i in items[:5])
            if len(items) > 5:
                vals += ", ..."
            parts.append(f"in: [{vals}]")

        # regex pattern
        for p in self.g.objects(pnode, SH.pattern):
            parts.append(f"/{p}/")

        return " | ".join(parts) if parts else "constraint"

    # ------------------------------------------------------------------
    # Recursive diagram builder
    # ------------------------------------------------------------------
    def _build(
        self,
        parent_id: str,
        node,
        lines: list[str],
        edges: list[str],
        depth: int = 0,
    ) -> None:
        """Walk *node* and emit Mermaid nodes/edges for every SHACL constraint found.

        Handles: sh:and, sh:or, sh:not, sh:property, sh:node, sh:sparql.
        Recurses into blank-node structures up to ``MAX_DEPTH``.
        """
        if depth > MAX_DEPTH:
            return

        # ---- sh:and ----
        for and_head in self.g.objects(node, SH["and"]):
            items = self._rdf_list(and_head)
            aid = self._nid("AND")
            lines.append(f'    {aid}{{"AND"}}:::andCls')
            edges.append(f"    {parent_id} --> {aid}")
            for item in items:
                self._build(aid, item, lines, edges, depth + 1)

        # ---- sh:or ----
        for or_head in self.g.objects(node, SH["or"]):
            items = self._rdf_list(or_head)
            oid = self._nid("OR")
            lines.append(f'    {oid}{{"OR"}}:::orCls')
            edges.append(f"    {parent_id} --> {oid}")
            for item in items:
                self._build(oid, item, lines, edges, depth + 1)

        # ---- sh:not ----
        for not_node in self.g.objects(node, SH["not"]):
            nid = self._nid("NOT")
            lines.append(f'    {nid}{{"NOT"}}:::notCls')
            edges.append(f"    {parent_id} --> {nid}")
            self._build(nid, not_node, lines, edges, depth + 1)

        # ---- sh:property ----
        for prop_node in self.g.objects(node, SH.property):
            pid = self._nid("P")
            label = self._esc(self._prop_label(prop_node))
            msg = self._msg(prop_node)
            if msg:
                label += f"<br/>{self._esc(msg, MAX_MSG_LEN)}"
            lines.append(f'    {pid}["{label}"]:::propCls')
            edges.append(f"    {parent_id} --> {pid}")
            # Recurse into the property's own sub-structure
            # (nested sh:or, sh:and, sh:property, sh:node, etc.)
            self._build(pid, prop_node, lines, edges, depth + 1)

        # ---- sh:node ----
        for nd in self.g.objects(node, SH.node):
            if isinstance(nd, URIRef):
                # Cross-reference to a named shape — show as link
                rid = self._nid("REF")
                lines.append(f'    {rid}[["{self._esc(self._qn(nd))}"]]:::refCls')
                edges.append(f"    {parent_id} --> {rid}")
            elif isinstance(nd, BNode):
                # Inline anonymous shape — recurse into it
                self._build(parent_id, nd, lines, edges, depth + 1)

        # ---- sh:sparql ----
        for sq in self.g.objects(node, SH.sparql):
            sid = self._nid("SQ")
            msg = self._msg(sq) or "SPARQL constraint"
            lines.append(f'    {sid}[/"{self._esc(msg, 100)}"/]:::sqCls')
            edges.append(f"    {parent_id} --> {sid}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def shape_to_mermaid(self, shape) -> str:
        """Generate a complete Mermaid flowchart string for one SHACL shape."""
        self._counter = 0

        # --- header info ---
        name = self._esc(self._qn(shape) if isinstance(shape, URIRef) else str(shape))

        targets = [self._qn(t) for t in self.g.objects(shape, SH.targetClass)]
        # SPARQL-based targets
        for tn in self.g.objects(shape, SH.target):
            if (tn, RDF.type, SH.SPARQLTarget) in self.g:
                targets.append("SPARQL target")

        desc = next((str(d) for d in self.g.objects(shape, SH.description)), None)

        header = name
        if targets:
            header += f"<br/>Target: {self._esc(', '.join(targets))}"
        if desc:
            header += f"<br/>{self._esc(desc, 100)}"

        # --- begin Mermaid output ---
        lines: list[str] = [
            "flowchart TD",
            # Class definitions for colour-coded nodes
            "    classDef rootCls fill:#e8daef,stroke:#8e44ad,stroke-width:2px,color:#333",
            "    classDef orCls fill:#fef9e7,stroke:#f39c12,stroke-width:2px,color:#333",
            "    classDef andCls fill:#eafaf1,stroke:#27ae60,stroke-width:2px,color:#333",
            "    classDef propCls fill:#ebf5fb,stroke:#2980b9,stroke-width:1px,color:#333",
            "    classDef sqCls fill:#fdedec,stroke:#e74c3c,stroke-width:1px,color:#333",
            "    classDef notCls fill:#fdedec,stroke:#e74c3c,stroke-width:2px,color:#333",
            "    classDef refCls fill:#f2f3f4,stroke:#7f8c8d,stroke-width:1px,color:#333",
            # Root node (stadium / pill shape)
            f'    ROOT(["{header}"]):::rootCls',
        ]
        edges: list[str] = []

        # If this is a standalone PropertyShape, show its own scalar constraints
        if (shape, RDF.type, SH.PropertyShape) in self.g:
            pid = self._nid("P")
            lines.append(f'    {pid}["{self._esc(self._prop_label(shape))}"]:::propCls')
            edges.append(f"    ROOT --> {pid}")

        # Recursively build the constraint tree
        self._build("ROOT", shape, lines, edges)

        return "\n".join(lines + edges)

    def all_diagrams(self) -> dict[str, str]:
        """Return ``{shape_label: mermaid_text}`` for every shape in the graph."""
        result: dict[str, str] = {}

        for shape in self.g.subjects(RDF.type, SH.NodeShape):
            label = self._qn(shape) if isinstance(shape, URIRef) else str(shape)
            result[label] = self.shape_to_mermaid(shape)

        for shape in self.g.subjects(RDF.type, SH.PropertyShape):
            label = self._qn(shape) if isinstance(shape, URIRef) else str(shape)
            if label not in result:  # avoid duplicates
                result[label] = self.shape_to_mermaid(shape)

        return result


# ===================================================================
# HTML generator
# ===================================================================
def make_html(diagrams: dict[str, str], title: str = "SHACL Shape Diagrams") -> str:
    """Generate a self-contained HTML page with Mermaid.js visualisation."""

    sections = []
    toc_items = []
    for i, (label, mmd) in enumerate(diagrams.items()):
        toc_items.append(
            f'<li><a href="#s{i}">{html_mod.escape(label)}</a></li>'
        )
        sections.append(
            f'<div class="sec" id="s{i}">\n'
            f"<h2>{html_mod.escape(label)}</h2>\n"
            f'<div class="mermaid">\n{html_mod.escape(mmd)}\n</div>\n'
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_mod.escape(title)}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0; padding: 20px; background: #f5f5f5;
  }}
  h1 {{ color: #333; text-align: center; margin-bottom: 30px; }}
  .sec {{
    background: #fff; border-radius: 8px; padding: 20px;
    margin-bottom: 28px; box-shadow: 0 2px 4px rgba(0,0,0,.1);
    overflow-x: auto;
  }}
  .sec h2 {{
    color: #555; border-bottom: 2px solid #e0e0e0;
    padding-bottom: 8px; font-size: 1.05em; word-break: break-all;
  }}
  .mermaid {{ display: flex; justify-content: center; }}
  .toc {{
    background: #fff; border-radius: 8px; padding: 20px;
    margin-bottom: 28px; box-shadow: 0 2px 4px rgba(0,0,0,.1);
  }}
  .toc h2 {{ margin-top: 0; }}
  .toc ul {{ list-style: none; padding: 0; columns: 2; }}
  .toc li {{ padding: 3px 0; }}
  .toc a {{ color: #1a73e8; text-decoration: none; }}
  .toc a:hover {{ text-decoration: underline; }}
  .legend {{
    display: flex; flex-wrap: wrap; gap: 12px; justify-content: center;
    margin-bottom: 28px;
  }}
  .legend span {{
    display: inline-block; padding: 4px 14px; border-radius: 6px;
    font-size: .85em;
  }}
</style>
</head>
<body>

<h1>{html_mod.escape(title)}</h1>

<div class="legend">
  <span style="background:#e8daef;border:2px solid #8e44ad">Shape (root)</span>
  <span style="background:#fef9e7;border:2px solid #f39c12">OR</span>
  <span style="background:#eafaf1;border:2px solid #27ae60">AND</span>
  <span style="background:#ebf5fb;border:1px solid #2980b9">Property</span>
  <span style="background:#fdedec;border:1px solid #e74c3c">SPARQL / NOT</span>
  <span style="background:#f2f3f4;border:1px solid #7f8c8d">Reference</span>
</div>

<div class="toc">
  <h2>Shapes ({len(diagrams)})</h2>
  <ul>{"".join(toc_items)}</ul>
</div>

{"".join(sections)}

<script>
mermaid.initialize({{
  startOnLoad: true,
  theme: 'default',
  flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }},
  securityLevel: 'loose'
}});
</script>
</body>
</html>"""


# ===================================================================
# Processing pipeline
# ===================================================================
def process(input_path: str, output_dir: str | None = None) -> None:
    """Parse SHACL file(s) and write .mmd + .html outputs."""

    # Collect input files
    if os.path.isfile(input_path):
        ttl_files = [input_path]
    elif os.path.isdir(input_path):
        ttl_files = sorted(
            glob.glob(os.path.join(input_path, "**/*.ttl"), recursive=True)
        )
    else:
        print(f"Error: '{input_path}' is not a valid file or directory.")
        sys.exit(1)

    if not ttl_files:
        print(f"No .ttl files found in '{input_path}'.")
        sys.exit(1)

    # Resolve output directory
    if output_dir is None:
        output_dir = (
            os.path.dirname(input_path) if os.path.isfile(input_path) else input_path
        )
    os.makedirs(output_dir, exist_ok=True)

    all_diagrams: dict[str, str] = {}

    for ttl_file in ttl_files:
        print(f"Processing: {ttl_file}")

        g = Graph()
        try:
            g.parse(ttl_file, format="turtle")
        except Exception as e:
            print(f"  Parse error: {e}")
            continue

        converter = SHACLtoMermaid(g)
        diagrams = converter.all_diagrams()

        if not diagrams:
            print("  No SHACL shapes found")
            continue

        print(f"  Found {len(diagrams)} shape(s)")

        # Save individual .mmd files
        base_name = os.path.splitext(os.path.basename(ttl_file))[0]
        for label, mmd_text in diagrams.items():
            safe_label = "".join(
                c if c.isalnum() or c in "._-" else "_" for c in label
            )
            mmd_path = os.path.join(output_dir, f"{base_name}_{safe_label}.mmd")
            with open(mmd_path, "w", encoding="utf-8") as f:
                f.write(mmd_text)
            print(f"    -> {mmd_path}")

            # Collect for combined HTML (prefix with filename for uniqueness)
            all_diagrams[f"{base_name} / {label}"] = mmd_text

    # Generate combined HTML visualisation
    if all_diagrams:
        html_path = os.path.join(output_dir, "shacl_diagrams.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(make_html(all_diagrams))
        print(f"\nHTML visualisation saved to: {html_path}")
        print(f"Total shapes visualised: {len(all_diagrams)}")
    else:
        print("\nNo SHACL shapes found in any input file.")


# ===================================================================
# CLI entry point
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Convert SHACL Turtle files to Mermaid diagrams with HTML visualisation"
    )
    parser.add_argument(
        "input_path",
        help="Path to a .ttl file or a directory containing .ttl files",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Output directory for .mmd and .html files (default: same as input)",
    )
    args = parser.parse_args()
    process(args.input_path, args.output_dir)


if __name__ == "__main__":
    main()
