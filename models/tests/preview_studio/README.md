# Photographic Preview review corpus

Manual B-rep fixtures for material and light-transport review. They are not CI
inputs. Outputs belong in ignored `tmp/`, never beside this source.

- `source.py::machined_bearing_housing`: bevels, recesses, counterbores, painted faces,
  repeated socket fasteners, rough aluminium, polished steel and bronze.
- `source.py::painted_pressure_regulator`: coated product body, ribbed polymer control,
  brass ports, a recessed ceramic gauge and glass crystal.
- `source.py::glass_sample_vessel`: thick glass walls, rolled rim, amber liquid, submerged
  metal samples and a separate knurled lid.
- `source.py::mixed_material_instrument`: open enclosure cavity, PCB, component leads,
  capacitors, fins, standoffs and copper turns in contact.

Run `exports.py --out /absolute/path/to/ignored/tmp/corpus` with this checkout's
development Python. The source remains four normal cadgen models; the export
script performs the explicit file actions for this standing review corpus.

The existing [`moonwatch` finishing sampler](../../moonwatch/src/finishing_sampler.py)
is an additional review case for fine chamfers, circular machining and tiny details.
It is not imported by these fixtures.
[`QDD actuator`](../../qdd_actuator/src/README.md) and
[`radial engine`](../../radial/src/README.md) are the existing medium/large assembly
cases. Prefer their saved engine documents or XBF files when available; a visual
review does not justify rebuilding an hour-long source model. Their generated
exports and pictures remain ignored outputs, and native XBF Preview is verified
separately from GLB Preview.

Compare production Preview against a baseline at the same camera, viewport, device
pixel ratio and studio settings. Review full images and native-resolution crops for
highlight shape, cavity lighting, glass thickness/refraction, silhouette and fine
edges, both at rest and during orbit. A completed render is not a visual-quality
verdict. Save captures and measurements under ignored `tmp/`.
