---
name: image-cad-preflight
description: Inspect reference images into a standard CAD Visual Spec before reconstructing 3D geometry. Focus on subtle surfaces, blends, silhouettes and section changes. Does not build CAD.
license: MIT
---

# Image-to-CAD visual preflight

Use when reference images are primary geometry sources for reconstruction. Keep
the original user request and original images in the **same main session**. The inspector adds evidence to that session; it never
replaces it or generates CAD. Image-free modeling, opening existing CAD and
inspiration-only images do not need this stage.

## Inspect

1. Resolve the original images to existing local paths without replacing or
   altering them. Create a project-local `.cad_context/` directory. Store the
   user's original request verbatim in `request.txt` there; do not send that
   whole request as executable inspector instructions. Use a short `--context`
   to identify the target part only when needed.
2. Run the helper with an available Python 3 interpreter. `<skill-dir>` is the
   absolute directory containing this SKILL.md. No CAD packages are needed.
   Isolated inspection requires a logged-in Codex CLI supporting `exec`,
   `--image`, `--output-schema`, `--output-last-message`, `--ephemeral`,
   `--sandbox`, `--skip-git-repo-check` and `--cd`. Other hosts, or users without
   this CLI, can use the main-session fallback below without installing Codex.

```bash
python "<skill-dir>/scripts/visual_preflight.py" \
  --image "/absolute/path/reference.png" \
  --request-file ".cad_context/request.txt" \
  --output ".cad_context/visual_spec.md" \
  --json-out ".cad_context/visual_spec.json"
```

Repeat `--image` for multiple views; order defines view IDs V1, V2, etc. Do not
add a model override unless the user has selected one. The child uses the
CLI-configured model, which may differ from the main session's model. `--dry-run` checks inputs and prints the planned command
without launching a child. It does not count as inspection.

The helper starts a fresh ephemeral `codex exec` in a temporary directory,
uses a read-only sandbox and the bundled strict output schema, then checks the
result locally before publishing it. It sends the prompt over stdin with image
flags last. It does not resume or fork the main session. Temporary working
context does not guarantee removal of global configuration or system guidance.

3. Continue only after a successful command. Read the generated Markdown.
   JSON contains the same inspection plus source hashes, request hash, mode and
   run ID. Keep these outputs in the current CAD project, never the plugin.

## Main-session fallback

If local image paths cannot be resolved, or the child CLI is unavailable or
fails, say so. Do not pretend an isolated child ran. If the original images are
visible to the main session, read [the inspector](references/visual_inspector.md)
and [the schema](references/visual_spec.schema.json), inspect them in this main
session and produce the schema-shaped JSON in `.cad_context/inspection.json`.
Then validate and render it with:

```bash
python "<skill-dir>/scripts/visual_preflight.py" \
  --from-json ".cad_context/inspection.json" \
  --image-label "Original in-chat image, view V1" \
  --request-file ".cad_context/request.txt" \
  --output ".cad_context/visual_spec.md" \
  --json-out ".cad_context/visual_spec.json"
```

Repeat `--image-label` for multiple in-chat views, or use `--image` for available
local files. This mode is explicitly labeled `main-session`; it has no isolation
claim. If the image itself is not accessible, report that limitation and do not
invent a spec. A failed command never authorizes reading old outputs.

## Return to CAD

Keep all three: **original user request + original images + CAD Visual Spec**.
Continue the `cad` skill in the original main session. If installed standalone,
return the spec to the caller for modeling. Do not hand the modeling job to the
inspector child.

- Explicit user requirements and specified dimensions control the design.
- Original images are the visual evidence. P0 observations are required review
  items, including low-confidence ones, not facts that outrank that evidence.
- Resolve image/spec conflicts explicitly using the cited view and visual basis.
  Confidence and construction importance are separate dimensions.
- UNKNOWN is missing evidence, not permission to invent exact dimensions,
  radii, hidden geometry or continuity. Label necessary modeling assumptions.
- Before building, note how each P0 affects construction. During the existing
  snapshot review, check P0/P1 against the resulting model and record unresolved
  differences in the project. Do not add unsupported geometry to satisfy a guess.

Completion means a successful validation and matching Markdown/JSON run IDs,
followed by reading the Markdown in the main session. File existence alone is
not completion. A previous spec can only be reused after checking that images,
request and target scope are unchanged.
