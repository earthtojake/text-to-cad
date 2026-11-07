// GENERATED from the library's document type registry (cad.registry): do not edit.
// Regenerate with `python -m cad.registry --js > packages/core/src/lib/documentTypes.generated.js`;
// tests/python/packages/cad/test_registry.py fails when this file and the registry differ.
export const DOCUMENT_TYPE_REGISTRY = Object.freeze({
  "operations": [
    "export",
    "snapshot",
    "inspect",
    "dfm",
    "fea",
    "drc",
    "erc",
    "validate"
  ],
  "views": [
    "document",
    "mesh",
    "drawing",
    "robot",
    "plot"
  ],
  "documentTypes": [
    {
      "id": "model",
      "title": "model",
      "wire": "model",
      "extensions": [],
      "mime": "",
      "view": "document",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "dfm"
      ],
      "decorator": true
    },
    {
      "id": "xbf",
      "title": "XBF",
      "wire": "xbf",
      "extensions": [
        ".xbf"
      ],
      "mime": "application/octet-stream",
      "view": "document",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "dfm",
        "fea"
      ],
      "decorator": true
    },
    {
      "id": "step",
      "title": "STEP",
      "wire": "step",
      "extensions": [
        ".step",
        ".stp"
      ],
      "mime": "application/step",
      "view": "document",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "dfm",
        "fea"
      ],
      "decorator": true
    },
    {
      "id": "stl",
      "title": "STL",
      "wire": "stl",
      "extensions": [
        ".stl"
      ],
      "mime": "model/stl",
      "view": "mesh",
      "operations": [
        "export",
        "snapshot",
        "dfm"
      ],
      "decorator": true
    },
    {
      "id": "glb",
      "title": "GLB",
      "wire": "glb",
      "extensions": [
        ".glb"
      ],
      "mime": "model/gltf-binary",
      "view": "mesh",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "dfm"
      ],
      "decorator": true
    },
    {
      "id": "threemf",
      "title": "3MF",
      "wire": "3mf",
      "extensions": [
        ".3mf"
      ],
      "mime": "model/3mf",
      "view": "mesh",
      "operations": [
        "export",
        "snapshot",
        "dfm"
      ],
      "decorator": true
    },
    {
      "id": "dxf",
      "title": "DXF",
      "wire": "dxf",
      "extensions": [
        ".dxf"
      ],
      "mime": "application/dxf",
      "view": "drawing",
      "operations": [
        "snapshot"
      ],
      "decorator": true
    },
    {
      "id": "urdf",
      "title": "URDF",
      "wire": "urdf",
      "extensions": [
        ".urdf"
      ],
      "mime": "application/xml; charset=utf-8",
      "view": "robot",
      "operations": [
        "snapshot",
        "validate"
      ],
      "decorator": false
    },
    {
      "id": "srdf",
      "title": "SRDF",
      "wire": "srdf",
      "extensions": [
        ".srdf"
      ],
      "mime": "application/xml; charset=utf-8",
      "view": "robot",
      "operations": [
        "snapshot",
        "validate"
      ],
      "decorator": false
    },
    {
      "id": "sdf",
      "title": "SDF",
      "wire": "sdf",
      "extensions": [
        ".sdf"
      ],
      "mime": "application/xml; charset=utf-8",
      "view": "robot",
      "operations": [
        "snapshot",
        "validate"
      ],
      "decorator": false
    },
    {
      "id": "kicad_pcb",
      "title": "KiCad PCB",
      "wire": "kicad_pcb",
      "extensions": [
        ".kicad_pcb"
      ],
      "mime": "text/plain; charset=utf-8",
      "view": "plot",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "drc"
      ],
      "decorator": false
    },
    {
      "id": "kicad_sch",
      "title": "KiCad schematic",
      "wire": "kicad_sch",
      "extensions": [
        ".kicad_sch"
      ],
      "mime": "text/plain; charset=utf-8",
      "view": "plot",
      "operations": [
        "export",
        "snapshot",
        "inspect",
        "erc"
      ],
      "decorator": false
    }
  ]
});
