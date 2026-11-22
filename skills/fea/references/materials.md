# Materials

Isotropic, linear, room temperature. A static study reads E, ν and yield, and density for a
`gravity` or `acceleration` load.

**The model's own material is the default.** A part solved from its `.xbf` with no `material` in
the study takes the material its model set (`part.material = bd_materials.metals.aluminum()`).
bd_materials gives each mechanical property as a range, and a study reads:

- **yield**: the range's low end, so the safety factor is against the weakest the material may be;
- **E and ν**: the middle of their ranges (they set the displacement, not whether the part holds);
- **density**: as given.

A one-part result's `material` says which: `"source": "document"` and the `ranges` each number
came from (an assembly's `parts` give each part's material and yield). Report the yield used and
that it is the low end of the range.

**A STEP carries a material's name and density, not its mechanics**, so a part solved from a STEP
with no study material is refused, naming the part. Solve the model's `.xbf` instead, or give the
numbers.

**A study's own numbers win** over the model's: a supplier's datasheet, a heat-treated grade the
model's material does not describe. Give them as the object [`material`](study-file.md#material)
describes, in `material` for every part or in `parts` for one (the result then says
`"source": "study"`). No table reads an alloy's numbers off its name, so a name alone is refused.
A part with neither a model material nor study numbers is refused, naming it: set its material in
the model (ask the person what it is made of), or ask for the numbers. Never pick a material to
make a study run.

For a directional material (printed layers, wood, a fibre block) give the modulus along the
direction that carries the load, say that you did, and report the answer as rough, with a larger
margin than for a machined metal: a printed polymer's strength varies by a factor of two or more
with layer adhesion, infill and orientation.
