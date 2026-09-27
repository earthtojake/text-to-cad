Modeling-tree fixtures contain STEP-derived SURF metadata, with unused binary
p-curve offsets removed from face loops. They contain no generator source.

- `phoneCase.json`: document SHA-256 `7493d9cb813c4959999cbaa2d8cc6e63ecf042eccdb056535137a0f61261ef48`, component `0795843faff191ac`.
- `prismatic.json`, `annular.json`, `revolved.json`: document SHA-256 `2df34f0c251892328329cfc527e8b530c2267ebcfb4acbd725397f4fa0ce6951`, components `10c27ff82080b266`, `5986f42e0abe3a5b`, `5f292bde48f70493` respectively.

The source STEP files remain unchanged. Fixtures are excluded from compiled UI exports.

- `externalPocketBoss.json`: actual STEP-derived geometry from [tpaviot/pythonocc-demos](https://raw.githubusercontent.com/tpaviot/pythonocc-demos/8158b217efc313889162e7c4dfefba87078d1270/assets/models/face_recognition_sample_part.stp), SHA-256 `de7b8a513ae923cd11de2323e798ac084cc94f9aa7d7a2a8adab65fc592f8d0b`. Complete 23-face body.

- `externalSplitBore.json`: actual STEP-derived geometry from [FreeCAD/FreeCAD](https://raw.githubusercontent.com/FreeCAD/FreeCAD/22af548376aed2d7b51bae18f3fcde3a2a2cf594/data/examples/Schenkel.stp), SHA-256 `69df4cb83831b2e0b9e9d7a04c72c893c6dcc82f2c18c4dd2f3280144a6c8088`. Two half-cylinder bore faces and their immediate support faces; support-face topology is intentionally partial.

- `roundedBox.json`, `ruledCabin.json`, `ruledBody.json`: SURF index plus float32
  payload from the same Ferrari STEP (`2df34f0c251892328329cfc527e8b530c2267ebcfb4acbd725397f4fa0ce6951`),
  components `fe5be8866fdd8f52`, `28535f794d294be8`, `0898bc86e1a0d4bf`. These
  exercise fillets, spline-encoded ruled sections, and lofts followed by blind cuts.

- `externalTransverseBracket.json` / `externalSplitShaft.json`: STEP-derived SURF
  indexes from pythonocc-as1.step, components `ebb0afa7fa4efacb` and
  `edd97418b949cbcc`. Cover transverse bores and semicylindrical export seams.
  Existing `externalPocketBoss.json` also covers verified stock/recess/boss/fillet
  reconstruction. No generator source participates in these recipes.
