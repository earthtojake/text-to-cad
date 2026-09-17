import assert from "node:assert/strict";
import test from "node:test";

import { parseSdf } from "./parseSdf.js";
import { solveUrdfLinkWorldTransforms, transformPoint } from "./kinematics.js";

class FakeElement {
  constructor(tagName, attributes = {}, children = [], text = "") {
    this.nodeType = 1;
    this.tagName = tagName;
    this.localName = String(tagName || "").split(":").pop();
    this.namespaceURI = null;
    this._attributes = { ...attributes };
    this.childNodes = children;
    this._text = String(text || "");
    for (const child of this.childNodes) {
      if (child && typeof child === "object") {
        child.parentNode = this;
      }
    }
  }

  getAttribute(name) {
    return Object.hasOwn(this._attributes, name) ? this._attributes[name] : null;
  }

  get textContent() {
    return `${this._text}${this.childNodes.map((child) => String(child?.textContent || "")).join("")}`;
  }
}

class FakeDocument {
  constructor(documentElement) {
    this.documentElement = documentElement;
  }

  querySelector(selector) {
    return selector === "parsererror" ? null : null;
  }
}

function el(tagName, attributes = {}, children = [], text = "") {
  return new FakeElement(tagName, attributes, children, text);
}

function textEl(tagName, text, attributes = {}) {
  return el(tagName, attributes, [], text);
}

function withFakeDomParser(document, callback) {
  const previous = globalThis.DOMParser;
  globalThis.DOMParser = class FakeDomParser {
    parseFromString() {
      return document;
    }
  };
  try {
    return callback();
  } finally {
    globalThis.DOMParser = previous;
  }
}

function meshVisual(linkName, uri, color = "0.168627 0.184314 0.2 1") {
  return el("visual", { name: `${linkName}_visual` }, [
    textEl("pose", "0 0 0 0 0 0", { relative_to: linkName }),
    el("geometry", {}, [
      el("mesh", {}, [
        textEl("uri", uri),
        textEl("scale", "0.001 0.001 0.001")
      ])
    ]),
    el("material", {}, [
      textEl("diffuse", color)
    ])
  ]);
}

function meshCollision(linkName, uri) {
  return el("collision", { name: `${linkName}_collision` }, [
    el("geometry", {}, [
      el("mesh", {}, [
        textEl("uri", uri)
      ])
    ])
  ]);
}

function link(name, { parent = "", pose = "0 0 0 0 0 0" } = {}) {
  const children = [
    textEl("pose", pose, parent ? { relative_to: parent } : {}),
    meshVisual(name, `meshes/${name}.stl`),
    meshCollision(name, `meshes/${name}_collision.stl`)
  ];
  return el("link", { name }, children);
}

function joint(index, parent, child, type = "revolute") {
  const axisChildren = [
    textEl("xyz", "0 0 1")
  ];
  if (type !== "continuous") {
    axisChildren.push(el("limit", {}, [
      textEl("lower", "-1.57079632679"),
      textEl("upper", "1.57079632679")
    ]));
  }
  return el("joint", { name: `joint_${index}`, type }, [
    textEl("parent", parent),
    textEl("child", child),
    textEl("pose", `${index * 0.01} 0 0 0 0 0`, { relative_to: parent }),
    el("axis", {}, axisChildren)
  ]);
}

function sdfRoot(children, attributes = { version: "1.12" }) {
  return el("sdf", attributes, children);
}

function parseWithRoot(root, sourceUrl = "/workspace/robots/so101.sdf") {
  return withFakeDomParser(new FakeDocument(root), () => parseSdf("<sdf />", { sourceUrl }));
}

function roundedPoint(point) {
  return point.map((value) => {
    const rounded = Math.round(value * 1000) / 1000;
    return Object.is(rounded, -0) ? 0 : rounded;
  });
}

test("parseSdf reads SO101-style model-level SDF robot data", () => {
  const links = [
    link("base_link"),
    ...Array.from({ length: 7 }, (_, index) => link(`link_${index + 1}`, {
      parent: index === 0 ? "base_link" : `link_${index}`
    }))
  ];
  const joints = Array.from({ length: 7 }, (_, index) => joint(
    index + 1,
    index === 0 ? "base_link" : `link_${index}`,
    `link_${index + 1}`,
    index === 6 ? "continuous" : "revolute"
  ));
  const root = sdfRoot([
    el("model", { name: "so101_new_calib" }, [...links, ...joints])
  ]);

  const sdfData = parseWithRoot(root);

  assert.equal(sdfData.robotName, "so101_new_calib");
  assert.equal(sdfData.rootLink, "base_link");
  assert.equal(sdfData.links.length, 8);
  assert.equal(sdfData.joints.length, 7);
  assert.equal(sdfData.links[0].visuals[0].meshUrl, "/workspace/robots/meshes/base_link.stl");
  assert.equal(sdfData.links[0].visuals[0].color, "#2b2f33");
  assert.equal(sdfData.links[0].collisions[0].meshUrl, "/workspace/robots/meshes/base_link_collision.stl");
  assert.deepEqual(sdfData.joints[0].axis, [0, 0, 1]);
  assert.equal(Math.round(sdfData.joints[0].minValueDeg), -90);
  assert.equal(Math.round(sdfData.joints[0].maxValueDeg), 90);
  assert.equal(sdfData.joints[6].type, "continuous");
  assert.equal(sdfData.motion, null);
  assert.equal(sdfData.srdf, null);
});

test("parseSdf preserves remote origins when resolving hosted mesh URIs", () => {
  const root = sdfRoot([
    el("model", { name: "hosted_robot" }, [
      link("base_link")
    ])
  ]);

  const sdfData = parseWithRoot(root, "https://blob.example.test/models2/robots/so101/robot.sdf");

  assert.equal(
    sdfData.links[0].visuals[0].meshUrl,
    "https://blob.example.test/models2/robots/so101/meshes/base_link.stl"
  );
  assert.equal(
    sdfData.links[0].collisions[0].meshUrl,
    "https://blob.example.test/models2/robots/so101/meshes/base_link_collision.stl"
  );
});

test("parseSdf preserves CAD occurrence ids encoded in visual names", () => {
  const root = sdfRoot([
    el("model", { name: "sample" }, [
      el("link", { name: "occ_node_001_base" }, [
        el("visual", { name: "o1_2_10_visual" }, [
          el("geometry", {}, [
            el("mesh", {}, [
              textEl("uri", "meshes/base.stl")
            ])
          ])
        ])
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);

  assert.equal(sdfData.links[0].visuals[0].instanceId, "o1_2_10_visual");
  assert.equal(sdfData.links[0].visuals[0].occurrenceId, "o1.2.10");
});

test("parseSdf resolves SDF link poses through native frame semantics", () => {
  const root = sdfRoot([
    el("model", { name: "robot" }, [
      link("base_link"),
      link("tool_link", { pose: "2 0 0 0 0 0" }),
      el("joint", { name: "base_to_tool", type: "fixed" }, [
        textEl("parent", "base_link"),
        textEl("child", "tool_link")
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(sdfData);

  assert.deepEqual(roundedPoint(transformPoint(linkWorldTransforms.get("tool_link"), [0, 0, 0])), [2, 0, 0]);
  assert.equal(sdfData.sdf.nativeFrameSemantics, true);
});

test("parseSdf preserves a native SDF joint frame offset from the child link", () => {
  const root = sdfRoot([
    el("model", { name: "robot" }, [
      link("base_link"),
      link("door_link", { pose: "2 0 0 0 0 0" }),
      el("joint", { name: "hinge", type: "revolute" }, [
        textEl("parent", "base_link"),
        textEl("child", "door_link"),
        textEl("pose", "-1 0 0 0 0 0"),
        el("axis", {}, [
          textEl("xyz", "0 0 1"),
          el("limit", {}, [
            textEl("lower", "-3.14159265359"),
            textEl("upper", "3.14159265359")
          ])
        ])
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(sdfData, { hinge: 90 });

  assert.deepEqual(roundedPoint(transformPoint(linkWorldTransforms.get("door_link"), [0, 0, 0])), [1, 1, 0]);
});

test("parseSdf converts joint axes expressed in another SDF frame into the joint frame", () => {
  const root = sdfRoot([
    el("model", { name: "robot" }, [
      link("base_link"),
      link("slider_link", { pose: "0 0 0 0 0 1.57079632679" }),
      el("joint", { name: "slide", type: "prismatic" }, [
        textEl("parent", "base_link"),
        textEl("child", "slider_link"),
        el("axis", {}, [
          textEl("xyz", "1 0 0", { expressed_in: "base_link" }),
          el("limit", {}, [
            textEl("lower", "-10"),
            textEl("upper", "10")
          ])
        ])
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(sdfData, { slide: 2 });

  assert.deepEqual(roundedPoint(transformPoint(linkWorldTransforms.get("slider_link"), [0, 0, 0])), [2, 0, 0]);
});

test("parseSdf rejects missing roots, missing models, and ambiguous model selections", () => {
  assert.throws(
    () => parseWithRoot(el("robot", { name: "not_sdf" })),
    /root element must be <sdf>/
  );
  assert.throws(
    () => parseWithRoot(sdfRoot([])),
    /requires one direct <model> or one <world>/
  );
  assert.throws(
    () => parseWithRoot(sdfRoot([el("model", { name: "a" }), el("model", { name: "b" })])),
    /multiple top-level models/
  );
  assert.throws(
    () => parseWithRoot(sdfRoot([el("world", { name: "default" })])),
    /world rendering currently requires exactly one direct <model>/
  );
});

test("parseSdf renders a single-model SDF world as static robot structure", () => {
  const root = sdfRoot([
    el("world", { name: "default" }, [
      el("model", { name: "robot" }, [
        link("base_link")
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);

  assert.equal(sdfData.robotName, "robot");
  assert.equal(sdfData.sdf.documentKind, "world");
  assert.equal(sdfData.sdf.worldName, "default");
  assert.equal(sdfData.motion, null);
});

test("parseSdf rejects duplicate links and duplicate joints", () => {
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [
        link("base_link"),
        link("base_link")
      ])
    ])),
    /Duplicate SDF link name/
  );
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [
        link("base_link"),
        link("tool_link", { parent: "base_link" }),
        el("joint", { name: "duplicate_joint", type: "fixed" }, [
          textEl("parent", "base_link"),
          textEl("child", "tool_link")
        ]),
        el("joint", { name: "duplicate_joint", type: "fixed" }, [
          textEl("parent", "base_link"),
          textEl("child", "tool_link")
        ])
      ])
    ])),
    /Duplicate SDF joint name/
  );
});

test("parseSdf reports simulator-only SDF elements as static metadata", () => {
  const root = sdfRoot([
    el("world", { name: "default" }, [
      el("include", {}, [
        textEl("uri", "model://other_robot"),
        textEl("name", "other_robot")
      ]),
      el("light", { name: "sun", type: "directional" }),
      el("physics", { name: "fast", type: "ode", default: "true" }),
      el("model", { name: "robot" }, [
        link("base_link"),
        el("sensor", { name: "camera", type: "camera" }),
        el("plugin", { name: "gz_controller", filename: "gz-sim-joint-controller-system" }),
        el("model", { name: "nested_payload" }, [
          link("payload_link")
        ])
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);
  const metadata = sdfData.sdf.staticMetadata;

  assert.equal(metadata.includes.length, 1);
  assert.equal(metadata.plugins.length, 1);
  assert.equal(metadata.sensors.length, 1);
  assert.equal(metadata.lights.length, 1);
  assert.equal(metadata.physics.length, 1);
  assert.equal(metadata.nestedModelCount, 1);
  assert.equal(metadata.plugins[0].filename, "gz-sim-joint-controller-system");
  assert.equal(sdfData.motion, null);
  assert.ok(metadata.warnings.some((warning) => warning.includes("does not execute simulator plugins")));
});

test("parseSdf rejects unsupported joint types", () => {
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [
        link("base_link"),
        link("tool_link", { parent: "base_link" }),
        el("joint", { name: "ball_joint", type: "ball" }, [
          textEl("parent", "base_link"),
          textEl("child", "tool_link")
        ])
      ])
    ])),
    /Unsupported SDF joint type/
  );
});

test("parseSdf ignores CAD Viewer input motion plugin channels as static metadata", () => {
  const root = sdfRoot([
    el("model", { name: "robot" }, [
      link("base_link"),
      link("wheel_link", { parent: "base_link" }),
      joint(1, "base_link", "wheel_link", "continuous"),
      el("plugin", { name: "cad_viewer_input_motion", filename: "cad-viewer-input-motion" }, [
        textEl("time_scale", "1.5"),
        el("channel", {
          joint: "joint_1",
          label: "Input wheel",
          waveform: "linear",
          rate_deg_per_sec: "120",
          offset_deg: "5"
        })
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);

  assert.equal(sdfData.motion, null);
  assert.equal(sdfData.sdf.staticMetadata.plugins.length, 1);
  assert.equal(sdfData.sdf.staticMetadata.plugins[0].customAnimation, true);
  assert.ok(sdfData.sdf.staticMetadata.warnings.some((warning) => warning.includes("input-motion plugins are ignored")));
});

test("parseSdf ignores CAD Viewer link pose playback tracks as static metadata", () => {
  const root = sdfRoot([
    el("model", { name: "robot" }, [
      link("base_link"),
      link("door_link", { parent: "base_link" }),
      joint(1, "base_link", "door_link", "fixed"),
      el("plugin", { name: "cad_viewer_input_motion", filename: "cad-viewer-input-motion" }, [
        textEl("time_scale", "2"),
        el("link_pose_playback", { loop: "true" }, [
          el("track", { link: "door_link", label: "Door" }, [
            el("key", { time: "0" }, [
              textEl("pose", "0 0 0 0 0 0", { relative_to: "base_link" })
            ]),
            el("key", { time: "1" }, [
              textEl("pose", "1 0 0 0 0 1.57079632679", { relative_to: "base_link" })
            ])
          ])
        ])
      ])
    ])
  ]);

  const sdfData = parseWithRoot(root);

  assert.equal(sdfData.motion, null);
  assert.equal(sdfData.sdf.staticMetadata.plugins.length, 1);
  assert.equal(sdfData.sdf.staticMetadata.plugins[0].customAnimation, true);
});

// Geometry the renderer cannot draw used to become a silent placeholder: the composer
// dropped it and the model rendered as empty space at exit 0. URDF has always thrown on
// unsupported visual geometry; SDF now matches it.
test("parseSdf refuses a visual mesh with no uri and a visual shape with no dimensions", () => {
  const withMeshNoUri = () => parseWithRoot(sdfRoot([
    el("model", { name: "robot" }, [
      el("link", { name: "base_link" }, [el("visual", {}, [el("geometry", {}, [el("mesh")])])])
    ])
  ]));
  assert.throws(withMeshNoUri, /SDF link base_link visual 1 is a <mesh> with no <uri>/);

  const withEmptyBox = () => parseWithRoot(sdfRoot([
    el("model", { name: "robot" }, [
      el("link", { name: "base_link" }, [el("visual", {}, [el("geometry", {}, [el("box")])])])
    ])
  ]));
  // A <box> IS drawable; saying "box is unsupported" would send the reader to the wrong place.
  assert.throws(withEmptyBox, /visual 1 is a <box> with missing or non-positive dimensions/);
});

test("parseSdf refuses a VISUAL shape the renderer has never drawn, naming the supported set", () => {
  for (const shape of ["capsule", "plane", "ellipsoid", "heightmap", "polyline"]) {
    const parse = () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [
        el("link", { name: "ground" }, [el("visual", {}, [el("geometry", {}, [el(shape)])])])
      ])
    ]));
    assert.throws(parse, new RegExp(`SDF link ground visual 1 uses <${shape}> geometry`), shape);
    assert.throws(parse, /Supported: box, cylinder, mesh, sphere/, shape);
  }
});

// Collision geometry is never drawn, so an undrawable one costs the picture nothing and must
// not block a load. A <plane> ground collision is the commonest shape in a real Gazebo world.
test("parseSdf loads a world whose COLLISION geometry it cannot draw, and counts it", () => {
  const sdfData = parseWithRoot(sdfRoot([
    el("model", { name: "world" }, [
      el("link", { name: "ground" }, [
        el("visual", { name: "v" }, [
          el("geometry", {}, [el("box", {}, [textEl("size", "10 10 0.1")])])
        ]),
        el("collision", { name: "c" }, [
          el("geometry", {}, [el("plane", {}, [textEl("size", "100 100")])])
        ])
      ]),
      el("link", { name: "pillar" }, [
        el("collision", { name: "c" }, [el("geometry", {}, [el("capsule")])]),
        el("collision", { name: "c2" }, [el("geometry", {}, [el("mesh")])])
      ])
    ])
  ]));

  const byName = new Map(sdfData.links.map((entry) => [entry.name, entry]));
  assert.deepEqual(byName.get("ground").visuals[0].primitive, { type: "box", size: [10, 10, 0.1] });
  assert.equal(byName.get("ground").collisions[0].unsupportedGeometry, "plane");
  assert.equal(byName.get("pillar").collisions[0].unsupportedGeometry, "capsule");
  assert.equal(byName.get("pillar").collisions[1].unsupportedGeometry, "mesh");
  // The count is the Viewer's non-blocking channel: its SDF sheet shows "Unsupported geom."
  assert.equal(sdfData.sdf.unsupportedCollisionCount, 3);
  assert.equal(sdfData.sdf.unsupportedVisualCount, 0);
});

test("parseSdf refuses a visual with no geometry at all", () => {
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [el("link", { name: "ghost" }, [el("visual", {}, [])])])
    ])),
    /SDF link ghost visual 1 has no <geometry>\. Give it one of: box, cylinder, mesh, sphere/
  );
});

test("parseSdf rejects unsupported pose frames", () => {
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "robot" }, [
        link("base_link"),
        el("link", { name: "tool_link" }, [
          textEl("pose", "1 0 0 0 0 0", { relative_to: "unrelated_frame" }),
          meshVisual("tool_link", "meshes/tool_link.stl")
        ]),
        el("joint", { name: "base_to_tool", type: "fixed" }, [
          textEl("parent", "base_link"),
          textEl("child", "tool_link")
        ])
      ])
    ])),
    /unknown frame|unsupported pose frame/
  );
});

// Box, cylinder and sphere are the ordinary way an SDF link carries geometry. Until the
// parser read them, every such visual became a placeholder with no `primitive`, the
// composer dropped it for having neither a primitive nor a mesh, and a model built that way
// rendered as empty space — exit 0, no warning, nothing on screen.
test("parseSdf reads box, cylinder and sphere link geometry", () => {
  const sdfData = parseWithRoot(sdfRoot([
    el("model", { name: "rig" }, [
      el("link", { name: "plate" }, [
        el("visual", { name: "plate_v" }, [
          el("geometry", {}, [el("box", {}, [textEl("size", "0.4 0.24 0.02")])]),
          el("material", {}, [textEl("diffuse", "0.85 0.15 0.12 1")])
        ])
      ]),
      el("link", { name: "mast" }, [
        el("visual", { name: "mast_v" }, [
          el("geometry", {}, [el("cylinder", {}, [
            textEl("radius", "0.03"),
            textEl("length", "0.18")
          ])])
        ])
      ]),
      el("link", { name: "lamp" }, [
        el("visual", { name: "lamp_v" }, [
          el("geometry", {}, [el("sphere", {}, [textEl("radius", "0.018")])])
        ])
      ])
    ])
  ]));

  const byName = new Map(sdfData.links.map((entry) => [entry.name, entry]));
  const plate = byName.get("plate");
  const mast = byName.get("mast");
  const lamp = byName.get("lamp");
  assert.deepEqual(plate.visuals[0].primitive, { type: "box", size: [0.4, 0.24, 0.02] });
  assert.equal(plate.visuals[0].unsupportedGeometry, undefined);
  // A `<material>` on a primitive visual reaches it, exactly as it does on a mesh visual.
  assert.equal(plate.visuals[0].color, "#d9261f");
  assert.deepEqual(mast.visuals[0].primitive, { type: "cylinder", radius: 0.03, length: 0.18 });
  assert.deepEqual(lamp.visuals[0].primitive, { type: "sphere", radius: 0.018 });
  assert.equal(sdfData.sdf.unsupportedVisualCount, 0);
});

test("parseSdf refuses a drawable VISUAL shape whose dimensions are degenerate", () => {
  assert.throws(
    () => parseWithRoot(sdfRoot([
      el("model", { name: "rig" }, [
        el("link", { name: "base_link" }, [
          el("visual", {}, [el("geometry", {}, [el("box", {}, [textEl("size", "0.4 0")])])])
        ])
      ])
    ])),
    /is a <box> with missing or non-positive dimensions/
  );
  // The same shape in a collision is counted, not refused.
  const sdfData = parseWithRoot(sdfRoot([
    el("model", { name: "rig" }, [
      el("link", { name: "base_link" }, [
        el("visual", {}, [el("geometry", {}, [el("box", {}, [textEl("size", "1 1 1")])])]),
        el("collision", {}, [el("geometry", {}, [el("cylinder", {}, [textEl("radius", "0.03")])])])
      ])
    ])
  ]));
  assert.equal(sdfData.links[0].collisions[0].unsupportedGeometry, "cylinder");
});

// The Viewer serves a description from `/__cad/asset?file=<path>`, so the mesh is relative
// to the QUERY. Resolving it against the PATH gave `/__cad/meshes/wedge.stl`, the backend
// 404'd it, and every SDF naming a mesh failed to load — while the URDF beside it, same
// relative path, loaded fine, because only the URDF parser knew about that route.
test("parseSdf resolves a mesh URI against a /__cad/asset description URL", () => {
  const sdfData = parseWithRoot(
    sdfRoot([
      el("model", { name: "rig" }, [
        el("link", { name: "boom" }, [
          el("visual", { name: "boom_v" }, [
            el("geometry", {}, [el("mesh", {}, [textEl("uri", "meshes/wedge.stl")])])
          ])
        ])
      ])
    ]),
    "/__cad/asset?file=%2Fworkspace%2Frobots%2Fworld.sdf&v=abc123"
  );

  assert.equal(
    sdfData.links[0].visuals[0].meshUrl,
    "/__cad/asset?file=%2Fworkspace%2Frobots%2Fmeshes%2Fwedge.stl&v=abc123",
    "the mesh keeps the asset route and the description's cache-busting v"
  );
});

test("parseSdf still resolves a mesh URI against a plain static URL", () => {
  const sdfData = parseWithRoot(
    sdfRoot([
      el("model", { name: "rig" }, [
        el("link", { name: "boom" }, [
          el("visual", { name: "boom_v" }, [
            el("geometry", {}, [el("mesh", {}, [textEl("uri", "../shared/wedge.stl")])])
          ])
        ])
      ])
    ]),
    "/workspace/robots/world.sdf"
  );

  assert.equal(sdfData.links[0].visuals[0].meshUrl, "/workspace/shared/wedge.stl");
});
