# Materials

Isotropic, linear, room temperature. A static study reads E, ν and yield, and density for a
`gravity` or `acceleration` load.

**The model's own material is the default.** A part solved from its `.xbf` with no `material` in
the study takes the material its model set (`part.material = bd_materials.metals.aluminum()`, as
`$cad` sets it). bd_materials gives each mechanical property as a range, and a study reads:

- **yield**: the range's low end, so the safety factor is against the weakest the material may be;
- **E and ν**: the middle of their ranges (they set the displacement, not whether the part holds);
- **density**: as given.

The result's `material` says which: `"source": "document"` and the `ranges` each number came from.
Report the yield used and that it is the low end of the range.

**A STEP carries a material's name and density, not its mechanics**, so a part solved from a STEP
with no study material is refused, naming the part. Solve the model's `.xbf` instead, or give the
numbers.

**A study's own numbers win** over the model's: a supplier's datasheet, a heat-treated grade the
model's material does not describe. Give them as an object, in `material` for every part or in
`parts` for one:

```json
{"name": "Aluminum 6061-T6", "E_MPa": 68900, "nu": 0.33, "yield_MPa": 276, "density_t_per_mm3": 2.7e-9}
```

`E_MPa`, `nu` and `yield_MPa` are required, `name` and `density_t_per_mm3` optional (the result
says `"source": "study"`). A name alone is refused: nothing reads an alloy's numbers off its name.
A part with neither a model material nor study numbers is refused, saying how to give it one: set
its material in the model (ask the user what it is made of), or ask for the numbers. Never pick a
material to make a study run.

For printed polymers the model's assumptions are loose: layer adhesion,
infill and orientation change stiffness and strength by a factor of two or
more. Say so, and use a larger safety factor than for a machined metal part.

A material must be the same in every direction. For a directional material (printed layers,
wood, a fibre block), give the modulus along the direction that carries the load, say that you did,
and treat the answer as rough.
