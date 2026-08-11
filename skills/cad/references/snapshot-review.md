# Snapshot review

Read this file when choosing saved CAD `scripts/snapshot` outputs for primary STEP/STP artifacts.

## Policy

Snapshot validation is mandatory. Every created or visibly updated primary STEP/STP part or assembly gets at least one reviewed PNG snapshot; deterministic checks passing is not a reason to skip. Use CAD `scripts/snapshot` rather than opening the viewer manually or using Playwright; snapshots are faster, lighter, more precise, and more agent-friendly. Use PNGs for static reviews and GIFs for motion/animation reviews, including STEP-module parameter animation.

Skip saved snapshots only when no visible geometry was created or updated, or no valid artifact exists:

- pure format/export requests where geometry is unchanged
- source changes that do not alter visible geometry
- inspection-only tasks (for example direct measurement questions) that create or update nothing
- failed Python or STEP generation before a valid artifact exists

When skipping, report the reason and the deterministic evidence that still ran.

Do not loop on snapshots. Rerender only when a source repair changed visible geometry or when a specific visual finding needs confirmation.

## Packet sizing

One PNG is enough for a simple static part. Use the small multi-view packet when semantic errors are plausible from shape complexity or prompt intent:

- assemblies or more than one body/part
- holes on multiple faces or multiple axes
- shells, internal cavities, bores, passages, open enclosures, or section-critical features
- ribs, gussets, bosses, standoffs, slots, cutouts, lightening holes, fins, blades, or repeated patterns
- source repairs after a geometry, boolean, selector, or feature failure
- prompts where "looks like the requested object" is part of the task
- deterministic checks pass but visible semantics are still uncertain

## Small packet

Prefer a single `view` JSON job with these outputs:

```json
{
  "input": "models/part.step",
  "mode": "view",
  "outputs": [
    { "path": "/tmp/render/iso.png", "camera": "iso" },
    { "path": "/tmp/render/iso_opposite.png", "camera": { "direction": [-1, 1, -0.8] } },
    { "path": "/tmp/render/top_ortho.png", "camera": "top" },
    { "path": "/tmp/render/front_ortho.png", "camera": "front" }
  ],
  "render": { "viewLabels": true, "padding": 0.12, "sizeProfile": "diagnostic" }
}
```

The two opposed isometric views guarantee every face appears in at least one image — rear, left, and bottom features are covered by default, not by suspicion. The top ortho is the primary pattern/symmetry check and the front ortho the profile check.

Set `input` to the primary STEP/STP artifact using a relative or absolute path. The snapshot CLI derives its internal render root from that input path. A `<name>.step.py` generator input always renders the generator's entry package, even when a same-stem exported `<name>.step` file exists beside it; pass the `.step` path explicitly only when you want the imported-STEP entry (which may trigger a slow first-time direct-import artifact build). It defaults to `theme: "snapshot"` and `display.mode: "solid"`. `snapshot` is a render-only theme — Workbench Light with the ground grid, origin axis and shadows removed, because in a still image those read as geometry rather than as orientation. It is not offered in the CAD Viewer's theme picker; pass `theme: "workbench-light"` to match the viewport exactly; labeled/section views default to 1600x1200 when dimensions are omitted. Use `render.sizeProfile: "assembly"` or `"assembly-large"` for complex assemblies that need 1800x1200 or 1920x1440. For CAD review packets, use still-image render modes `view` and `section`; set `display.mode` to `solid`, `transparent`, `hidden_edges`, `hidden_lines_removed`, or `wireframe` when the visual check benefits from explicit CAD linework.

Use `--focus '#o1.2' ...` to emphasize specific part or subassembly occurrence refs — in `view`/`orbit` renders the focused refs keep full opacity while the rest of the assembly is ghosted in place (framing and context are preserved); in `section` mode focus isolates the refs entirely. Use `--hide '#o1.2' ...` to omit parts from the render in every mode. Do not combine focus and hide in the same snapshot command or job. These filters accept occurrence refs only, not face, edge, vertex, or shape selectors.

The snapshot CLI appends one shared UTC seconds timestamp before each output file extension when saving a packet, so readable paths like `iso_solid.png` become names such as `iso_solid_20260527T163012Z.png`.

## Targeted additions

Add views only when the brief or a failure mode calls for them:

- reference-image reproduction: one snapshot from the reference image's viewpoint for side-by-side comparison
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

Final reports should include the generated snapshot PNG/GIFs or the documented skip reason, and state which deterministic checks support any visual finding.
