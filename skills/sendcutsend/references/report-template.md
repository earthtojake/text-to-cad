# SendCutSend Validation Report Template

Use this structure when the user asks for a review, validation, preflight, or manufacturing readiness report.

## Context

- File: `<path>`
- Assumed service: `DXF laser sheet cutting` or `STEP CNC routing`
- Order context: material, thickness, primary process, finish, quantity, secondary operations
- Date checked: `<YYYY-MM-DD>`

## Sources Checked

List the official SendCutSend URLs consulted as Markdown links, with the access date and each JSON's `_meta.generated_at`. This section is a bibliography, not a substitute for row-level citations.

## Geometry Facts

File type, units, extents/bounding box, entity/body counts, layers, unsupported entities, obvious open/duplicate geometry, and parsing limitations.

For bent 2D files, include bend geometry facts from the exported file: bend-line count and layers, individual bend line lengths, nearest non-bend cut geometry for each bend line, local flange depths, bend-line span coverage, bend-adjacent cut geometry, insufficient contact/support observations, and any split/interrupted/common-axis bend observations.

For bent STEP/STP files, include measured sheet thickness when available and the extracted bend-radius set.

## Findings

Use one row per issue. In `Rule source`, link the specific official page or JSON file that defines the requirement being checked, and include the field path when the source is JSON. Example: `[sendcutsend-specs.json](https://cdn.sendcutsend.com/specs/sendcutsend-specs.json) materials[sku=ALU-063].cutting_specs.min_hole_size`.

| Status | Check | Evidence | Rule source | Recommendation |
| --- | --- | --- | --- | --- |
| ✅ pass, ❌ fail or ❓ need more info | requirement name | file fact | Markdown link to specific rule doc/table, or `Direct file inspection` | concrete next action |

## Verdict

Use a limited verdict:

- `Ready to upload for this assumed context`: every required check passes or is explicitly outside the selected service
- `Needs edits before upload`: a required check is `❌ fail`
- `Insufficient context to validate`: none fails, and one is `❓ need more info`
