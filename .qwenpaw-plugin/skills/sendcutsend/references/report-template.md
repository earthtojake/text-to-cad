# SendCutSend Validation Report Template

Use this structure when the user asks for a review, validation, preflight, or manufacturing readiness report.

## Context

- File: `<path>`
- Assumed service: `DXF laser sheet cutting` or `STEP CNC routing`
- Order context: material, thickness, primary process, finish, quantity, secondary operations
- Date checked: `<YYYY-MM-DD>`

## Sources Checked

List official SendCutSend URLs used for the checks as Markdown links. Include only sources actually consulted. Include the access date and JSON `_meta.generated_at` values when available. The findings table must also link the specific rule source for each row, so this section is a bibliography, not a substitute for row-level citations.

## Geometry Facts

Summarize facts from `$cad` inspection when available and targeted `build123d`/`ezdxf` inspection code: file type, units, extents/bounding box, entity/body counts, layers, unsupported entities, obvious open/duplicate geometry, and parsing limitations.

If the reviewed upload was generated or updated in this workflow, include the `$cad-viewer` viewer link when available.

For bent 2D files, include bend geometry facts from the exported file: bend-line count and layers, individual bend line lengths, nearest non-bend cut geometry for each bend line, local flange depths, bend-line span coverage, bend-adjacent cut geometry, insufficient contact/support observations, and any split/interrupted/common-axis bend observations. Use those facts for comparison against the current material/thickness service page.

For bent STEP/STP files, include measured sheet thickness when available and the extracted bend-radius set. Compare bend radii to the selected material/SKU only when that order context is known.

## Findings

Use one row per issue. In `Rule source`, link the specific official page or JSON file that defines the requirement being checked, and include the field path when the source is JSON. Example: `[sendcutsend-specs.json](https://cdn.sendcutsend.com/specs/sendcutsend-specs.json) materials[sku=ALU-063].cutting_specs.min_hole_size`. Prefer exact SKU-specific sources over generic guide text. If no external rule applies, write `Direct file inspection`.

| Status | Check | Evidence | Rule source | Recommendation |
| --- | --- | --- | --- | --- |
| ✅ pass / ❌ fail / ❓ need more info | requirement name | file fact | Markdown link to specific rule doc/table, or `Direct file inspection` | concrete next action |

## Verdict

Use a limited verdict:

- `Ready to upload for this assumed context`
- `Needs edits before upload`
- `Insufficient context to validate`

Never use a ready verdict if any required current official requirement check is marked `❌ fail` or `❓ need more info`. Use `Ready to upload for this assumed context` only when every required cited check has sufficient order context, source evidence, measured file facts, and passes or is explicitly outside the selected service. Until an explicit SendCutSend UI classification model is deliberately added, treat measured upload risks and manufacturability issues as `❌ fail`.
