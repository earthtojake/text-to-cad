# Official SendCutSend Source Map

Read this for the URLs to fetch, what to record about each fetch, and which source wins when two disagree.

## Core Entry Points

- Ordering guide (ordering flow, accepted file formats, plain-language design rules, general service explanations): https://cdn.sendcutsend.com/specs/sendcutsend-ordering-guide.md
- Catalog JSON (orderability by SKU: material name, thickness, stock status, cutting process, min/max part size, available services; hardware items; finish options): https://cdn.sendcutsend.com/specs/sendcutsend-catalog.json
- Engineering specs JSON (design values by SKU: tolerances, minimum hole/bridge/edge values, bending parameters, tapping, countersinking, hardware insertion, dimple forming, finishing constraints, material properties): https://cdn.sendcutsend.com/specs/sendcutsend-specs.json

## Provenance To Capture

- Source URL
- Access date
- JSON `_meta.schema_version`
- JSON `_meta.generated_at`
- JSON `_meta.source_data_generated_at` when present
- Field path for row-level citations, such as `sendcutsend-specs.json materials[sku=ALU-063].cutting_specs.min_hole_size`

## Conflict Handling

When source facts conflict, rely on the first of these that answers, and record the conflict and the page you relied on:

1. material/thickness/service-specific configurator or current quote/upload result
2. exact SKU entry in engineering specs JSON
3. exact SKU entry in catalog JSON
4. ordering guide
5. broader official SendCutSend human-readable page, only when the three source files are insufficient
