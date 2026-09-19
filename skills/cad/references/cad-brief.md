# Interpreting a CAD request

Use this reference when modeling from prose, reference images or technical
drawings. Record only the dimensions, interfaces, outputs and assumptions needed
to construct and check the requested geometry. A simple part may need a sentence;
a complex assembly may benefit from a dimension/interface checklist. There is
no required brief format, and direct inspection or export needs no modeling brief.

Clarify missing or conflicting information when it materially affects the result,
especially a mating interface or required scale. Otherwise proceed with explicit
assumptions. Do not ask the user to fill out a template.

## Reference images

- Distinguish reproducing a part from using an image as design inspiration.
- Establish scale from a supplied dimension or known reference when available.
  Unscaled images can guide proportions; they do not establish fit dimensions.
- Record inferred dimensions as assumptions. Ask for scale when fit depends on it.
- For reproduction, compare a snapshot from a similar viewpoint with the image.

## Technical drawings

- Read units, projection convention, revision and notes; identify each view and
  section before mapping dimensions to model axes.
- Prefer explicit dimensions over image proportions. Resolve conflicting
  dimensioned sources rather than silently choosing one.
- Preserve multiplicity (`4X`), `TYP.`, threads, counterbores, countersinks and
  internal depths shown in sections. Track the requirements for later checks.
- Derive unspecified geometry from constraints where possible. Treat dimensions
  estimated from a drawing image as assumptions, never as verified callouts.
- Verify the specified dimensions against saved geometry using Python
  measurements, or explicitly report those not verified. See
  [inspection and validation](inspection-and-validation.md).

Before modeling, identify the relevant source/output paths, units, coordinate
convention and functional interfaces. Choose construction and validation methods
that make the controlling dimensions easy to express and check.
