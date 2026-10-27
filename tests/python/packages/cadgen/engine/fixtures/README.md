# Saved-format fixtures

`xbf8_materials.xbf` is a 15.9 KiB BinXCAF file written by **published cadgen
0.8.0**, build123d 0.11.1 and cadquery-ocp-novtk 7.9.3.1.1. It exercises the real
old OCCT binary reader; a document produced by the current engine and relabelled
`xbf/8` cannot replace it. `xbf8_materials.json` records the producer versions,
SHA-256, original writer/build closure and the released reader's expected
structure, physics and appearance.

The fixture contains only two small boxes and a cylinder, in a nested assembly.
The pin is placed twice, with distinct instance colours. They share one physical
material card but have distinct part/face colours and
visual-material references. One visual has different core PBR factors from the
shared physical card. The legacy metadata covers Pa-based mechanical properties,
density, thermal properties, source, standard, description, anisotropy,
transmission, clearcoat and emission. Its closure deliberately points to absent
source/data files. Tests read saved bytes; they never regenerate the fixture or
execute the missing model.

To regenerate deliberately, use a separate old environment, never the checkout's
current development interpreter:

```sh
python3.13 -m venv /tmp/cadgen-xbf8-fixture
/tmp/cadgen-xbf8-fixture/bin/python -m pip install cadgen==0.8.0
/tmp/cadgen-xbf8-fixture/bin/python tests/python/packages/cadgen/engine/fixtures/make_xbf8_fixture.py
```

The generator checks all three package versions before writing. Review the XBF
and provenance JSON together. It invokes no daemon and uses no sample corpus.
