# FireBIM Ontology (FBO)

This folder contains the FireBIM ontology, modelling concepts and terminology used in fire-safety regulations across several European countries, together with their mappings to IFC.

All files share the same base namespace `https://ontology.firebim.be/ontology/` and use Turtle (`.ttl`) syntax.

## Files

### Core

- **[fbo.ttl](fbo.ttl)** — Core FireBIM ontology (`fbo:`). Country-agnostic / European-level concepts (e.g. `ActiveFireProtection`, `AreaFireCompartment`), shared properties, datatypes, units (QUDT), time-stamps (time last edited in Notion for now) and the Notion identifiers. Country-specific terms link back here via `fbo:hasSubitem` / `fbo:isLinkedTo`.

- **[firebim_ontology_unified.ttl](firebim_ontology_unified.ttl)** — Single merged graph containing the core ontology, all country modules and the IFC mapping module. Use this when you want to load everything at once instead of importing the pieces individually.

### Country modules

Each module defines the national fire-safety vocabulary, with terms linked to the core `fbo:` concepts and (where available) to IFC.

- **[fbo-be.ttl](fbo-be.ttl)** — Belgium (`fbo-be:`)
- **[fbo-nl.ttl](fbo-nl.ttl)** — Netherlands (`fbo-nl:`)
- **[fbo-dk.ttl](fbo-dk.ttl)** — Denmark (`fbo-dk:`)
- **[fbo-pt.ttl](fbo-pt.ttl)** — Portugal (`fbo-pt:`)
- **[fbo-lt.ttl](fbo-lt.ttl)** — Lithuania (`fbo-lt:`)

Country terms typically carry labels and definitions in both English and the national language, references to the source regulation (`fbo:hasDocumentReference`), domain tags, and IFC mappings.

### IFC mapping

- **[fbo-ifc.ttl](fbo-ifc.ttl)** — IFC mapping module (`fbo-ifc:`). Named individuals describe how an FBO concept is expressed in IFC: the IFC class / predefined type, property set, datatype and whether the mapping is a buildingSMART standard property. Each individual is connected back to the FBO terms it represents via `fbo-ifc:mapsToTerm`.

## Namespaces

| Prefix | IRI |
| --- | --- |
| `fbo` | `https://ontology.firebim.be/ontology/fbo#` |
| `fbo-be` | `https://ontology.firebim.be/ontology/fbo-BE#` |
| `fbo-nl` | `https://ontology.firebim.be/ontology/fbo-NL#` |
| `fbo-dk` | `https://ontology.firebim.be/ontology/fbo-DK#` |
| `fbo-pt` | `https://ontology.firebim.be/ontology/fbo-PT#` |
| `fbo-lt` | `https://ontology.firebim.be/ontology/fbo-LT#` |
| `fbo-ifc` | `https://ontology.firebim.be/ontology/fbo-ifc#` |

## Source of truth

The ontology is edited in Notion and exported to Turtle by [NotionToOntology.py](../NotionToOntology.py). Each term retains its `fbo:hasNotionID` and `fbo:hasNotionURL` so the TTL files can be regenerated from Notion at any time — edit Notion, not the `.ttl` files directly!!!
