# Snapshot review

Read this file when choosing saved CAD `scripts/snapshot` outputs for primary STEP/STP artifacts after deterministic CAD validation.

## Principle

CAD Viewer links are the live handoff layer and should be returned for every generated or modified supported artifact when `$cad-viewer` is available. Saved snapshots are ALWAYS required for visual verification/review when creating or visibly updating primary STEP/STP parts or assemblies and should be included in final responses when generated. Do not skip snapshots for speed, convenience, confidence, or because deterministic checks passed. Use CAD `scripts/snapshot` over opening the viewer manually or using Playwright; snapshots are faster, lighter, more precise, and more agent-friendly. Snapshots complement STEP generation, `scripts/inspect`, measurements, alignment checks, frames, and diffs.

Skip saved snapshots only when no visible geometry was created or updated:

- pure format/export requests where geometry is unchanged
- source changes that do not alter visible geometry
- direct measurement questions answerable with `scripts/inspect`
- failed Python or STEP generation before a valid artifact exists

Simple created or visibly updated STEP/STP parts ALWAYS get at least one PNG snapshot. For skipped cases, generate or inspect the explicit target, hand off generated or modified artifacts to `$cad-viewer` when available, and report the evidence.

## Risk triggers

After STEP/STP generation and geometric validation pass, one PNG may be enough for a simple static part. Use a small snapshot packet when semantic errors are plausible from shape complexity or prompt intent:

- assemblies or more than one body/part
- holes on multiple faces or multiple axes
- shells, internal cavities, bores, passages, open enclosures, or section-critical features
- ribs, gussets, bosses, standoffs, slots, cutouts, lightening holes, fins, blades, or repeated patterns
- source repairs after a geometry, boolean, selector, or feature failure
- prompts where "looks like the requested object" is part of the task
- deterministic checks pass but visible semantics are still uncertain

Do not loop on snapshots. Rerender only when a source repair changed visible geometry or when a specific visual finding needs confirmation. Use PNGs for static reviews and GIFs for motion/animation reviews, including STEP-module parameter animation.

## Small packet

Use a small packet first. Prefer a single `view` JSON job with these outputs:

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso_solid.png", "camera": "iso", "width": 1600, "height": 1200 },
    { "path": "/tmp/render/front_ortho.png", "camera": "front", "width": 1600, "height": 1200 },
    { "path": "/tmp/render/top_ortho.png", "camera": "top", "width": 1600, "height": 1200 },
    { "path": "/tmp/render/right_ortho.png", "camera": "right", "width": 1600, "height": 1200 }
  ],
  "render": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

Set `input` to the primary STEP/STP artifact using a relative or absolute path. The snapshot CLI derives its internal render root from that input path. It defaults to `appearance: "workbench"` and `display.mode: "solid"`, matching CAD Viewer; labeled/section views default to 1600x1200 when dimensions are omitted. Use `render.sizeProfile: "assembly"` or `"assembly-large"` for complex assemblies that need 1800x1200 or 1920x1440. For CAD review packets, use still-image render modes `view` and `section`; set `display.mode` to `solid`, `transparent`, `hidden_edges`, `hidden_lines_removed`, or `wireframe` when the visual check benefits from explicit CAD linework.

Use `--focus '#o1.2' ...` to render only specific part or subassembly occurrence refs, or `--hide '#o1.2' ...` to omit them. Do not combine focus and hide in the same snapshot command or job. These filters accept occurrence refs only, not face, edge, vertex, or shape selectors.

The snapshot CLI appends one shared UTC seconds timestamp before each output file extension when saving a packet, so readable paths like `iso_solid.png` become names such as `iso_solid_20260527T163012Z.png`.

## Targeted additions

Add views only when the brief or a failure mode calls for them:

- rear or bottom camera: features may be hidden from the default packet
- `section`: shell, bore, internal cavity, passage, blind hole, enclosure, or wall/floor relationship
- `display.mode: "solid"`: shaded CAD view with explicit edge linework
- `display.mode: "rendered"`: shaded material view without edge overlay
- `display.mode: "transparent"`: overlap, collision, enclosure readability, or hidden contact checks when transparency adds information and wireframe is too noisy
- `display.mode: "hidden_edges"`: opaque shaded context with hidden/occluded CAD edges visible through solids
- `display.mode: "hidden_lines_removed"`: line-focused review where hidden/occluded edges should be suppressed
- `display.mode: "wireframe"`: internal overlap, hidden interference, or assembly collision suspicion when full triangle wire is useful
- labeled or annotated review: use supported CAD Viewer refs, selections, screenshots, or GUI review links

Exploded or labeled review is an intent, not a render mode. Satisfy it through supported CAD Viewer mechanisms, supported JSON job settings, or the GUI link.

## Diagnostic review

Visual review is diagnostic, not authoritative. Convert every visual concern into a follow-up geometry check before using it as a validation claim:

- hole pattern appears asymmetric -> measure hole centers and compare offsets
- lid, child part, or occurrence appears offset -> inspect frames and mating deltas
- gusset, boss, standoff, rib, or plate may be floating -> inspect solid count, labels, connectivity, contact, or relevant distances
- cavity, bore, or blind hole looks wrong -> run section review, then measure wall thickness, depth, or through-condition
- repeated pattern looks uneven -> measure pattern centers, angular spacing, or occurrence frames

Final reports should say whether the `$cad-viewer` viewer link was returned, include generated snapshot PNG/GIFs or explain why no snapshot applied, and state which deterministic checks support any visual finding.
