# Official SendCutSend Source Map

Use these sources as live evidence, not as a stable API. Field coverage, value types, and `N/A` usage can vary. Before making pass/fail claims, cite the exact source URL and, for JSON facts, the field path used.

## Core Entry Points

- Ordering guide: https://cdn.sendcutsend.com/specs/sendcutsend-ordering-guide.md
- Catalog JSON: https://cdn.sendcutsend.com/specs/sendcutsend-catalog.json
- Engineering specs JSON: https://cdn.sendcutsend.com/specs/sendcutsend-specs.json

Fetch these URLs directly before each review. Use the current response bodies as the evidence for material/service checks, and cite the URL plus the access date in the report.

## Source Roles

- Ordering guide: use for ordering flow, accepted file formats, plain-language design rules, and general service explanations.
- Catalog JSON: use for orderability facts such as material SKUs, material names, thicknesses, stock status, cutting process, min/max part size, available services, hardware items, and finish options.
- Engineering specs JSON: use for SKU-keyed design validation facts such as tolerances, minimum hole/bridge/edge values, bending parameters, tapping, countersinking, hardware insertion, dimple forming, finishing constraints, and material properties.

## Provenance To Capture

- Source URL
- Access date
- JSON `_meta.schema_version`
- JSON `_meta.generated_at`
- JSON `_meta.source_data_generated_at` when present
- Field path for row-level citations, such as `sendcutsend-specs.json materials[sku=ALU-063].cutting_specs.min_hole_size`

## Conflict Handling

Prefer exact SKU joins across catalog and specs. If source facts conflict or a field is missing, unparsable, or `N/A`, report the uncertainty and mark the dependent row `❓ need more info` unless another more specific, cited source resolves it.

Use this precedence for source facts:

1. material/thickness/service-specific configurator or current quote/upload result
2. exact SKU entry in engineering specs JSON
3. exact SKU entry in catalog JSON
4. ordering guide
5. broader official SendCutSend human-readable page, only when the three source files are insufficient

Record the conflict and the page you relied on.
