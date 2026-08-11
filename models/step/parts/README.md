# STEP Parts

Single-body (or otherwise atomic) `<name>.step.py` generators — one generator
file per model, no project folder, no `children=` multi-part assembly. Larger
multi-part designs live in [`../assemblies/`](../assemblies/README.md) instead;
see that README for the assembly/part split rule.

## Structured fixtures

More structured than the compact examples below, each exercising a distinct
modeling surface. Useful for repeatable geometry generation, import/export, and
viewer behavior checks.

- `rectangular_calibration_block.step.py` — calibration block with four holes.
- `circular_flange.step.py` — flange with a bolt-hole pattern.
- `l_bracket.step.py` — L-bracket with gussets and two hole directions.
- `stepped_shaft_keyway.step.py` — stepped shaft with a keyway.
- `open_top_electronics_enclosure.step.py` — open-top enclosure with bosses.
- `clevis_bracket_lightening_cutouts.step.py` — aerospace-style clevis bracket.
- `radial_engine_cylinder.step.py` — radial-engine cylinder with cooling fins.

The spiral staircase and planetary gear stage from this set build multi-part
compounds, so they live in `../assemblies/` as `spiral_staircase.step.py` and
`planetary_gear_stage.step.py`.

- `part_common.py`: shared helper functions (`safe_fillet`, `safe_chamfer`,
  `circular_edges`, `polar_point`, `trapezoid_tooth_profile`, …) used by the
  fixtures above. `../assemblies/planetary_gear_stage.step.py` also imports it,
  via a `sys.path` insert pointing back at this directory.

## Simple examples

Compact part generators covering shapes not already represented above:

1. Cylindrical spacer sleeve with a central through-bore and rounded rim edges.
2. Square mounting block with a vertical through-hole and two side clearance holes.
3. Gusset plate with a triangular web, base holes, and softened perimeter edges.
4. Rectangular clamp block with a split slot and two transverse screw holes.
5. Shaft collar with a central bore, radial set-screw hole, and chamfered faces.
6. Pulley wheel with a central hub, outer groove, and circular through-bore.
7. Spur gear blank with central bore, raised hub, and simplified perimeter teeth.
8. Flywheel disk with central bore, annular rim, and lightening holes.
9. Cam follower roller with central bearing bore and rounded outer profile.
10. Small enclosure cover with raised rim, corner screw holes, and shallow recessed center.
11. Cylindrical cap with hollow interior, top boss, and rounded external edges.
12. Retainer plate with elongated slot, two circular holes, and chamfered perimeter.
13. Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern.
14. T-slot slider block with central channel, side relief cuts, and mounting holes.
15. Mounting plate with central circular cutout, elongated side slot, four corner holes, and rounded edges.
16. Basic shape mating test fixture for assembly-helper surface and collision checks.

A flat rectangular plate and a U/clevis bracket are intentionally omitted here
because the structured fixtures above already carry richer versions.

- `simple_model_library.py`: shared build123d implementation helpers used by
  the simple-example generators.

## Other single-file parts

- `centrifugal_impeller.step.py`, `electronics_enclosure_base.step.py`: single
  standalone demo parts (originally from `models/fun/`), more expressive than
  the structured fixtures but still one monolithic body.
- `research_humanoid.step.py`: a single-body GPT-5.6 humanoid concept
  (originally from `models/experiments/gpt-5.6-sol/`). The other two
  humanoid concepts from that set (`compact_humanoid`, `sculpted_humanoid`)
  build multi-part assemblies and live in `../assemblies/`.

## Files

- `*.step.py`: build123d generator source for each model.
- `*.step`: STEP output, written on demand via `scripts/gen --write`.
- `__cadgen__/`: per-folder cadgen output home written beside the sources,
  holding the generated render/selector packages. Gitignored and rebuilt on
  demand — never commit it.
