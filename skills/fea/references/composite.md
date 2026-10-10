# Composite (`composite`, lite)

It answers "will this carbon or glass fibre plate hold, and which ply goes first" for a flat
laminated part: plies of a unidirectional ply material (a lamina) stacked at angles. The plain word
is Composite.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): linear (small deflections, every ply elastic up to failure),
no delamination and no progressive damage (the answer is the first ply to fail), and classical
laminate theory's assumptions (plies perfectly bonded, each in plane stress: through-thickness
stresses are not judged). Say them whenever you quote a number from it.

## When to use it

- A flat panel, skin, plate, lid or bracket plate laid up from plies: carbon/epoxy, glass/epoxy,
  aramid. The user knows the layup (or you can ask for it: angles, ply thickness, ply material).
- "Which ply fails first", "how far does the panel bend", "is [0/90]s enough or do I need ±45s".
- Not for: a curved shell, a part with ribs, steps in thickness or bosses (the part must be a flat
  plate of even thickness, or the study is refused with a sentence saying so); sandwich panels with
  a foam or honeycomb core (no core model); delamination, impact damage, buckling of the laminate,
  or anything after the first ply fails.
- A solid block of one directional material (wood, a printed part treated as orthotropic, a single
  crystal) is not a layup: give `static` or `modal` an orthotropic material instead
  ([materials.md](materials.md#orthotropic-materials)).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys) (but no `material`: the
plies carry their own):

- `fixtures` and `loads`: as `static` ([linear-static.md](linear-static.md)); a body load needs
  every ply material's `density_t_per_mm3`. A skin face's load acts on the plate, a side face's on
  its edge; a fixed side face clamps that edge.
- `laminae`: the ply materials by name. Each needs `E1_MPa` (along the fibres), `E2_MPa` (across
  them), `nu12`, `G12_MPa` and five strengths, all positive: `Xt_MPa`, `Xc_MPa` (along the fibres,
  tension and compression), `Yt_MPa`, `Yc_MPa` (across them) and `S_MPa` (in-plane shear).
  Optional: `G13_MPa` (default G12), `G23_MPa` (default E2 / (2 (1 + nu23))), `nu23` (default
  nu12), `density_t_per_mm3`, `name`. Each default is an assumption of transverse isotropy, and the
  result lists the ones it used (a `lamina_assumed` finding). Take every number from the prepreg's
  datasheet; never make them up.
- `layup`: the plies **from the bottom face up**, each `{"material", "angle_deg", "thickness_mm"}`.
  `material` names a lamina in `laminae`, or is a lamina object itself. The plies' thicknesses must
  add up to the plate's thickness (within 2 %).
  - The bottom face is the one the laminate's normal points away from; that normal is the plate's,
    turned so its largest component is positive: for a plate lying in XY, ply 1 is on the −Z face.
    For a symmetric layup the order does not matter.
  - `angle_deg` (−180 to 180) is measured from the 0° direction, turning toward 90° (the normal
    × 0°): for a plate in XY with the default axis, +45° points between +X and +Y.
- `layup_axis` (optional): the 0° direction as `[x, y, z]`, laid into the plate. Default: global X
  (global Y for a plate that faces X).
- Checks:
  - `ply_failure`: the worst ply anywhere, by its failure index, against 1. Optional `criterion`:
    `"tsai_wu"` or `"max_stress"`; with none, the larger of the two. Fails over 1, close past 0.9.
    Row line "Worst ply 3 (+45°), failure index 0.82"; titles "A ply fails" / "Close to failing" /
    "Every ply holds". With no `view.checks` the study is judged by `{"kind": "ply_failure"}`.
  - `displacement`: `limit_mm`, optional `faces` (as static).
  - No `stress` check: a laminate has no single yield strength; the failure index is its strength
    check.
- No load control (`load_scale` is not a drive): the Tsai-Wu index is quadratic in the stress, so
  it does not scale with the load. View drives: `field` (`failure_index`, `von_mises`,
  `displacement`), `deformation`, `threshold`. With no view: the field and the deformation.

A carbon/epoxy panel, [0/90]s, clamped on two edges under a light pressure (T300/5208, Tsai and
Hahn's textbook lamina):

```json
{"analysis": "composite",
 "laminae": {"t300": {"E1_MPa": 181000, "E2_MPa": 10300, "nu12": 0.28, "G12_MPa": 7170,
                      "Xt_MPa": 1500, "Xc_MPa": 1500, "Yt_MPa": 40, "Yc_MPa": 246, "S_MPa": 68,
                      "density_t_per_mm3": 1.6e-9}},
 "layup": [{"material": "t300", "angle_deg": 0,  "thickness_mm": 0.25},
           {"material": "t300", "angle_deg": 90, "thickness_mm": 0.25},
           {"material": "t300", "angle_deg": 90, "thickness_mm": 0.25},
           {"material": "t300", "angle_deg": 0,  "thickness_mm": 0.25}],
 "fixtures": [{"faces": ["#o1.f1", "#o1.f2"]}],
 "loads": [{"faces": ["#o1.f6"], "type": "pressure", "pressure_MPa": 0.001}]}
```

## How it solves

- **Thin plate** (thickness under 5 % of its smaller span): its mid-surface as a Reissner-Mindlin
  shell (the same MITC3 triangles as static's shell idealisation), with classical laminate
  theory's stiffness: A, B and D from the plies (Q̄ = T(θ)ᵀ Q T(θ) per ply, A = Σ Q̄ t,
  B = Σ Q̄ (z₂² − z₁²)/2, D = Σ Q̄ (z₂³ − z₁³)/3) and the plies' transverse shear (5/6 Σ G t). The
  fields are mapped onto the real part for the Viewer. This is the method itself, not a ladder
  step; the result says `"method": "shell"` and a `composite_method` finding.
- **Thick plate**: meshed as a solid, every point taking its ply's 3D orthotropic stiffness by its
  height. Ply interfaces need not follow the elements: keep the element size near the ply
  thickness for an answer that resolves each ply (`mesh.size_mm`).
- Each ply's in-plane stresses in its own fibre axes (σ1, σ2, τ12) are judged at its top and bottom
  (thick: at every integration point inside it):
  - Tsai-Wu index F1 σ1 + F2 σ2 + F11 σ1² + F22 σ2² + F66 τ12² + 2 F12 σ1 σ2, with F1 = 1/Xt − 1/Xc,
    F2 = 1/Yt − 1/Yc, F11 = 1/(Xt Xc), F22 = 1/(Yt Yc), F66 = 1/S², F12 = −½ √(F11 F22);
  - max-stress index, the largest of σ1/Xt (or −σ1/Xc), σ2/Yt (or −σ2/Yc) and |τ12|/S.
- Fields: `failure_index` (the envelope over the plies, at each point of the plate), `von_mises`
  (the plies' in-plane von Mises, enveloped), `displacement`.
- The summary carries `method`, the `layup` (plies, `notation` such as "[0/90]s", thickness),
  `max_failure_index`, `worst_ply` (number, angle, material, criterion, both indices, its σ1, σ2,
  τ12 and where), every ply's maxima under `plies`, and for the shell the laminate's A, B and D
  under `detail`.

## How to judge the answer (hand checks)

- **ABD.** For [0/90]s with plies of thickness t0 (h = 4 t0): A11 = A22 = (Q11 + Q22)/2 · h,
  A12 = Q12 h, A66 = Q66 h, B = 0, D11 = (7 Q11 + Q22)/8 · h³/12, D22 = (Q11 + 7 Q22)/8 · h³/12,
  D12 = Q12 h³/12, D66 = Q66 h³/12, with Q11 = E1/(1 − ν12ν21), Q22 = E2/(1 − ν12ν21),
  Q12 = ν12 Q22, Q66 = G12. Compare `summary.detail.D`.
- **Deflection.** A long plate clamped along its two long edges a apart bends like a clamped-clamped
  beam per unit width: centre w = q a⁴ / (384 D11). Transverse shear adds about
  q a² / (8 · 5/6 · Σ G13 t), small when the span is over about 50 thicknesses. Simply supported
  edges are not available (fixtures clamp).
- **One ply.** Take the worst ply's σ1, σ2, τ12 from the summary and evaluate Tsai-Wu by hand: it
  must give `worst_ply.tsai_wu`.

## Limits

- Linear, small strain and small deflection; a thin plate that deflects more than about its
  thickness is stiffer in reality (membrane action) than this says.
- No delamination, no interlaminar (through-thickness) stresses judged, no progressive damage:
  the first ply failure is reported, and nothing after it.
- CLT: perfectly bonded plies, each in plane stress; transverse shear by a single 5/6 factor.
- Flat plates of even thickness only; one laminate per part; no assemblies.
- The ply-by-ply failure index does not scale with the load (Tsai-Wu is quadratic): to find the
  load at failure, run again at another load, or read the max-stress index, which is linear.

## Ladder (when it is big)

The thin path is already small: it takes no rung. The thick (solid) path takes, in order:

- `iterative`: AMG + CG, or matrix-free CG, on the layered stiffness (no accuracy cost);
- `local_refine`: a coarse pass, then fine only where the failure index peaked; its words quote how
  far the peak failure index moved between passes;
- `symmetry`: a half or a quarter when the part, its fixtures and loads are symmetric and every ply
  is its own mirror image about the plane (0° and 90° plies about planes along their axes; a ±45°
  ply is not, so a ±45 layup is never cut).

Report every step with its words and accuracy note, as the result gives them.
