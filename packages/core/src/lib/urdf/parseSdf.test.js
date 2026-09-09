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

test("parseSdf keeps unsupported geometry as static placeholders", () => {
  const sdfData = parseWithRoot(sdfRoot([
    el("model", { name: "robot" }, [
      el("link", { name: "base_link" }, [
        el("visual", {}, [
          el("geometry", {}, [el("mesh")])
        ]),
        el("collision", {}, [
          el("geometry", {}, [el("box")])
        ])
      ])
    ])
  ]));

  assert.equal(sdfData.sdf.unsupportedVisualCount, 1);
  assert.equal(sdfData.sdf.unsupportedCollisionCount, 1);
  assert.equal(sdfData.links[0].visuals[0].unsupportedGeometry, "mesh");
  assert.equal(sdfData.links[0].collisions[0].unsupportedGeometry, "box");
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
