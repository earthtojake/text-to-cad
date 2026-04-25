# Models

This directory is the project-local CAD workspace for this harness.

## Inventory

Reusable CAD and URDF workflow rules live in:

- [`../skills/cad/SKILL.md`](../skills/cad/SKILL.md)
- [`../skills/urdf/SKILL.md`](../skills/urdf/SKILL.md)

Create only the subdirectories the current project actually uses. When this
directory gains project-specific inventory, dependency notes, preferred rebuild
roots, or durable quirks, keep those notes compact and local to this file.

## Source Of Truth

- Edit generator Python sources or imported STEP/STP files first.
- Treat STEP, STL, DXF, GLB/topology, and URDF outputs as derived artifacts.
- Regenerate explicit targets with the CAD or URDF skill tools.
- Keep temporary review images outside `models/`, usually under `/tmp/...`.

## Mimo Monitor Case — Project Map

Two parallel shell families share the same source frame:

- `mimo_case_geometry.py` — the original organic, single-shell mimo case (back puck, side buttons, exploded view, original screen + bottom port + speaker holes). Driven from `mimo_pcb_geometry.py`.
- `mimo_case_print_ready_geometry.py` — clamshell variant for 3D printing. Reuses the original shell silhouette (84×86×24.7, plan radius 18.2, face fillet 10.0) and adds a Z-plane split, seam ring, snap tabs, alignment pins, PCB standoffs.

Entry points (all regenerable via `gen_step_part` or `gen_step_assembly`):

| Entry | Source | Purpose |
| --- | --- | --- |
| `mimo_case.step` | `mimo_case.py` | Assembled (visual) shell + buttons + back puck |
| `mimo_case_shell.step` | `mimo_case_shell.py` | Bare shell, both halves split at SEAM_Y |
| `mimo_case_exploded.step` | `mimo_case_exploded.py` | Exploded assembly (assembly target) |
| `mimo_case_pcb_integration.step` | `mimo_case_pcb_integration.py` | PCB sitting in the original case |
| `mimo_case_print_layout.step` | `mimo_case_print_layout.py` | Original case parts laid flat for printing |
| `mimo_case_print_ready.step` | `mimo_case_print_ready.py` | Print-ready clamshell halves only |
| `mimo_case_print_ready_assembled.step` | `mimo_case_print_ready_assembled.py` | Print-ready clamshell + PCB |
| `mimo_case_print_ready_print_layout.step` | `mimo_case_print_ready_print_layout.py` | Print-ready halves laid flat for printing |
| `mimo_pcb.step` | `mimo_pcb.py` | PCB driven from `mimo-board/dist/index/circuit.json` |

## Source Frame (read before editing)

Both shell files use the same axis convention:

- **+X** → screen-right
- **+Y** → screen-up. `BOTTOM_Y = -CASE_HEIGHT/2` is the bottom edge (USB-C lives here). `TOP_Y = +CASE_HEIGHT/2` is the top edge.
- **+Z** → out of the screen toward the user. `BACK_Z = 0` is the back face. `FRONT_Z = TOTAL_DEPTH` is the front face (screen recess lives here).

`viewer_aligned()` is a pure translation (no rotation) by `(0, +CASE_HEIGHT/2, -TOTAL_DEPTH/2)`, so the source frame **is** the world frame the viewer shows.

### `Plane.XZ` / `Plane.YZ` gotcha

build123d's `Plane.XZ` has its normal pointing in **−Y**, and `Plane.YZ` has its normal in **−X**. So `BuildSketch(Plane.XZ.offset(BOTTOM_Y - 0.05))` does **not** put the sketch at `y = -43.05`; it puts it at `y = +43.05` (TOP_Y face) and `extrude(amount=d)` pushes further in −Y.

If you want a feature on the BOTTOM_Y face (or any other "expected −Y" face), build the plane explicitly:

```python
plane = Plane(origin=(0, BOTTOM_Y - 0.05, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
```

Same trap applies for `Plane.YZ` — use explicit `Plane(...)` whenever the side you want is on the negative axis. `Plane.XY` is the only "intuitive" one (normal +Z).

## Workflow Hooks

- Validate dimension changes: `validate_assembled_bounds` (mimo_case_geometry.py) and `validate_usb_alignment` (mimo_pcb_geometry.py) both derive expectations from constants. If they fail, fix the derivation, not the expected tuple.
- Inspect placement before/after a change: use `cadref planes models/<entry> --json` to enumerate major coplanar groups by axis. This catches "feature ended up on the wrong face" errors in seconds.
- Render verification: `snapshot models/.<entry>.step/model.glb --views isometric,front,bottom --out-dir /tmp/cad-renders/...`. The new snapshot CLI takes GLB or STL only — point it at the package-local model.glb, not the Python source.
