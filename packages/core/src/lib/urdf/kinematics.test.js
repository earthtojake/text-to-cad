import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDefaultUrdfJointValues,
  buildUrdfVisualParts,
  clampJointValueDeg,
  jointMotionTransform,
  linkOriginInFrame,
  multiplyTransforms,
  posedJointLocalTransform,
  resolveUrdfJointValues,
  solveUrdfLinkWorldTransforms,
  transformPoint
} from "./kinematics.js";

function translationTransform(x, y, z) {
  return [
    1, 0, 0, x,
    0, 1, 0, y,
    0, 0, 1, z,
    0, 0, 0, 1
  ];
}

function scaleTransform(factor) {
  return [
    factor, 0, 0, 0,
    0, factor, 0, 0,
    0, 0, factor, 0,
    0, 0, 0, 1
  ];
}

function rotationZTransform(angleDeg) {
  const angleRad = (angleDeg * Math.PI) / 180;
  const cosine = Math.cos(angleRad);
  const sine = Math.sin(angleRad);
  return [
    cosine, -sine, 0, 0,
    sine, cosine, 0, 0,
    0, 0, 1, 0,
    0, 0, 0, 1
  ];
}

function partMesh(bounds, color = null) {
  const vertices = new Float32Array([
    0, 0, 0,
    1, 0, 0,
    0, 1, 0
  ]);
  const colors = color
    ? new Float32Array([
      ...color,
      ...color,
      ...color
    ])
    : new Float32Array(0);
  return {
    vertices,
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    indices: new Uint32Array([0, 1, 2]),
    bounds,
    colors,
    has_source_colors: colors.length === vertices.length
  };
}

function rounded(values) {
  return Array.from(values).map((value) => {
    const roundedValue = Math.round(value * 1000) / 1000;
    return Object.is(roundedValue, -0) ? 0 : roundedValue;
  });
}

function srgbToLinear(value) {
  return value <= 0.04045
    ? value / 12.92
    : ((value + 0.055) / 1.055) ** 2.4;
}

function linearHexTriplet(hexColor) {
  return [
    srgbToLinear(Number.parseInt(hexColor.slice(1, 3), 16) / 255),
    srgbToLinear(Number.parseInt(hexColor.slice(3, 5), 16) / 255),
    srgbToLinear(Number.parseInt(hexColor.slice(5, 7), 16) / 255)
  ];
}

function repeatedTriplet(triplet) {
  return [
    ...triplet,
    ...triplet,
    ...triplet
  ];
}

function sampleUrdf() {
  return {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:base",
            label: "base",
            instanceId: "base",
            partFileRef: "base-part",
            color: "#2b2f33",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      },
      {
        name: "arm_link",
        visuals: [
          {
            id: "arm_link:arm",
            label: "arm",
            instanceId: "arm",
            partFileRef: "arm-part",
            color: "#a4abb3",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      },
      {
        name: "tool_link",
        visuals: [
          {
            id: "tool_link:tool",
            label: "tool",
            instanceId: "tool",
            partFileRef: "tool-part",
            color: "#a4abb3",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: [
      {
        name: "base_to_arm",
        type: "continuous",
        parentLink: "base_link",
        childLink: "arm_link",
        originTransform: translationTransform(10, 0, 0),
        axisInJointFrame: [0, 0, 1],
        defaultValueDeg: 0,
        minValueDeg: -180,
        maxValueDeg: 180
      },
      {
        name: "arm_to_tool",
        type: "fixed",
        parentLink: "arm_link",
        childLink: "tool_link",
        originTransform: translationTransform(0, 5, 0),
        axisInJointFrame: [],
        defaultValueDeg: 0,
        minValueDeg: 0,
        maxValueDeg: 0
      },
      {
        name: "limited_joint",
        type: "revolute",
        parentLink: "tool_link",
        childLink: "aux_link",
        originTransform: translationTransform(0, 0, 0),
        axisInJointFrame: [1, 0, 0],
        defaultValueDeg: 0,
        minValueDeg: -45,
        maxValueDeg: 60
      }
    ]
  };
}

test("zero-pose solving reproduces authored default transforms", () => {
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(sampleUrdf(), buildDefaultUrdfJointValues(sampleUrdf()));

  assert.deepEqual(transformPoint(linkWorldTransforms.get("arm_link"), [0, 0, 0]), [10, 0, 0]);
  assert.deepEqual(transformPoint(linkWorldTransforms.get("tool_link"), [0, 0, 0]), [10, 5, 0]);
});

test("rotating the shoulder changes only the shoulder subtree", () => {
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(sampleUrdf(), { base_to_arm: 90 });

  assert.deepEqual(transformPoint(linkWorldTransforms.get("base_link"), [0, 0, 0]), [0, 0, 0]);
  assert.deepEqual(transformPoint(linkWorldTransforms.get("arm_link"), [0, 0, 0]), [10, 0, 0]);
  assert.deepEqual(transformPoint(linkWorldTransforms.get("tool_link"), [0, 0, 0]).map((value) => Math.round(value * 1000) / 1000), [5, 0, 0]);
});

test("link origin can be expressed in another link frame", () => {
  const urdf = sampleUrdf();

  assert.deepEqual(
    linkOriginInFrame(urdf, { base_to_arm: 0 }, "tool_link", "base_link").map((value) => Math.round(value * 1000) / 1000),
    [10, 5, 0]
  );
  assert.deepEqual(
    linkOriginInFrame(urdf, { base_to_arm: 90 }, "tool_link", "arm_link").map((value) => Math.round(value * 1000) / 1000),
    [0, 5, 0]
  );
});

test("fixed joints do not create default controls or motion", () => {
  const defaults = buildDefaultUrdfJointValues(sampleUrdf());

  assert.equal(Object.hasOwn(defaults, "arm_to_tool"), false);
  assert.equal(clampJointValueDeg(sampleUrdf().joints[1], 25), 0);
});

test("joint clamping respects revolute and continuous limits", () => {
  assert.equal(clampJointValueDeg(sampleUrdf().joints[0], 270), 270);
  assert.equal(clampJointValueDeg(sampleUrdf().joints[0], -240), -240);
  assert.equal(clampJointValueDeg(sampleUrdf().joints[2], 90), 60);
  assert.equal(clampJointValueDeg(sampleUrdf().joints[2], -90), -45);
});

test("prismatic mimic joints follow a revolute master in native URDF units", () => {
  const urdf = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      { name: "base_link", visuals: [] },
      { name: "driver_link", visuals: [] },
      { name: "right_slider", visuals: [] },
      { name: "left_slider", visuals: [] }
    ],
    joints: [
      {
        name: "driver_joint",
        type: "revolute",
        parentLink: "base_link",
        childLink: "driver_link",
        originTransform: translationTransform(0, 0, 0),
        axisInJointFrame: [0, 0, 1],
        defaultValueDeg: 0,
        minValueDeg: 0,
        maxValueDeg: 180
      },
      {
        name: "right_slide",
        type: "prismatic",
        parentLink: "base_link",
        childLink: "right_slider",
        originTransform: translationTransform(0, 0, 0),
        axisInJointFrame: [-1, 0, 0],
        defaultValueDeg: 0,
        minValueDeg: 0,
        maxValueDeg: 0.05,
        mimic: { joint: "driver_joint", multiplier: 0.01, offset: 0 }
      },
      {
        name: "left_slide",
        type: "prismatic",
        parentLink: "base_link",
        childLink: "left_slider",
        originTransform: translationTransform(0, 0, 0),
        axisInJointFrame: [1, 0, 0],
        defaultValueDeg: 0,
        minValueDeg: 0,
        maxValueDeg: 0.05,
        mimic: { joint: "driver_joint", multiplier: 0.01, offset: 0 }
      }
    ]
  };

  const defaults = buildDefaultUrdfJointValues(urdf);
  const linkWorldTransforms = solveUrdfLinkWorldTransforms(urdf, { driver_joint: 90 });
  const travel = Math.round(((Math.PI / 2) * 0.01) * 1000000) / 1000000;

  assert.deepEqual(Object.keys(defaults), ["driver_joint"]);
  assert.deepEqual(rounded(transformPoint(linkWorldTransforms.get("right_slider"), [0, 0, 0])), rounded([-travel, 0, 0]));
  assert.deepEqual(rounded(transformPoint(linkWorldTransforms.get("left_slider"), [0, 0, 0])), rounded([travel, 0, 0]));
});

test("joint origin rotation reorients the motion axis from joint frame into parent space", () => {
  const joint = {
    type: "continuous",
    originTransform: rotationZTransform(90),
    axisInJointFrame: [0, 1, 0],
    defaultValueDeg: 0,
    minValueDeg: -180,
    maxValueDeg: 180
  };

  const transformedPoint = transformPoint(posedJointLocalTransform(joint, 90), [0, 0, 1]).map((value) => Math.round(value * 1000) / 1000);

  assert.deepEqual(transformedPoint, [0, 1, 0]);
});

test("a joint's local transform is its static frame, then its motion alone, then its child offset", () => {
  // A scene graph poses by writing the MOTION factor and nothing else, so the three
  // factors must compose to exactly what the solver multiplies through.
  const revolute = {
    type: "revolute", originTransform: rotationZTransform(90), preMotionTransform: translationTransform(0, 0, 0.2),
    postMotionTransform: translationTransform(0.05, 0, 0), axis: [0, 1, 0], defaultValueDeg: 0, minValueDeg: -60, maxValueDeg: 60
  };
  for (const value of [0, 25, -200]) {
    assert.deepEqual(
      posedJointLocalTransform(revolute, value),
      multiplyTransforms(multiplyTransforms(revolute.preMotionTransform, jointMotionTransform(revolute, value)), revolute.postMotionTransform)
    );
  }
  assert.deepEqual(jointMotionTransform(revolute, -200), jointMotionTransform(revolute, -60), "clamped as the solver clamps it");
  const slider = { type: "prismatic", axis: [0, 0, 2], defaultValueDeg: 0, minValueDeg: 0, maxValueDeg: 0.3 };
  assert.deepEqual(rounded(transformPoint(jointMotionTransform(slider, 0.25), [0, 0, 0])), [0, 0, 0.25]);
  assert.deepEqual(jointMotionTransform({ type: "fixed" }, 40), translationTransform(0, 0, 0), "a fixed joint does not move");
});

test("resolved joint values clamp driven joints and solve mimic followers from their master", () => {
  const urdf = {
    joints: [
      { name: "driver", type: "revolute", defaultValueDeg: 0, minValueDeg: -90, maxValueDeg: 90 },
      { name: "follower", type: "prismatic", defaultValueDeg: 0, minValueDeg: 0, maxValueDeg: 0.01, mimic: { joint: "driver", multiplier: 0.01, offset: 0 } },
      { name: "spin", type: "continuous", defaultValueDeg: 0 },
      { name: "weld", type: "fixed", defaultValueDeg: 0 }
    ]
  };
  const resolved = resolveUrdfJointValues(urdf, { driver: 400, follower: 99, spin: 725, weld: 12 });
  assert.deepEqual([...resolved.keys()], ["driver", "follower", "spin", "weld"]);
  assert.equal(resolved.get("driver"), 90);
  assert.equal(resolved.get("follower"), 0.01, "from its master, then to its own limit; a value written for it is ignored");
  assert.equal(resolved.get("spin"), 725);
  assert.equal(resolved.get("weld"), 0);
  assert.equal(resolveUrdfJointValues(urdf).get("driver"), 0, "no value is the declared default");
});

// A description's visuals as the parts a robot's scene is built from. The scene poses them
// (robotScene.test.js holds it to the solver); these hold what a part carries.
test("visual parts keep the robot's link meshes in their own units and frames, the visual's transform beside them", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      { name: "base_link", visuals: [{ id: "base_link:visual", partFileRef: "link-mesh", localTransform: scaleTransform(0.001) }] },
      { name: "second_link", visuals: [{ id: "second_link:visual", partFileRef: "link-mesh", localTransform: scaleTransform(0.001) }] }
    ],
    joints: [
      { name: "fixed_joint", type: "fixed", parentLink: "base_link", childLink: "second_link", originTransform: translationTransform(0.3, 0, 0) }
    ]
  };
  const linkMesh = partMesh({ min: [0, 0, 0], max: [100, 10, 10] });
  const parts = buildUrdfVisualParts(urdfData, new Map([["link-mesh", linkMesh]]));

  assert.deepEqual(parts.map((part) => [part.id, part.linkName, part.sourceMeshKey]),
    [["base_link:visual", "base_link", "link-mesh"], ["second_link:visual", "second_link", "link-mesh"]]);
  assert.equal(parts[0].sourceMesh, linkMesh, "the loaded mesh itself, never a copy");
  assert.equal(parts[1].sourceMesh, linkMesh);
  assert.deepEqual(parts[0].bounds, { min: [0, 0, 0], max: [100, 10, 10] }, "in the mesh file's own units");
  assert.equal(parts[0].localTransform[0], 0.001, "the <mesh scale> lives in the part's transform");
  assert.deepEqual([parts[0].vertexCount, parts[0].triangleCount], [3, 1]);
  assert.equal("transform" in parts[0], false, "a part is not placed: the scene graph places it");
});

test("visual parts build primitive visuals without external mesh assets", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [{ name: "base_link", visuals: [{ id: "base_link:v1", label: "box", primitive: { type: "box", size: [2, 4, 6] },
      color: "#a4abb3", localTransform: translationTransform(0, 0, 0) }] }],
    joints: []
  };

  const [part] = buildUrdfVisualParts(urdfData, new Map());

  assert.deepEqual([part.vertexCount, part.triangleCount], [24, 12]);
  assert.deepEqual(part.bounds, { min: [-1, -2, -3], max: [1, 2, 3] });
  assert.deepEqual([part.name, part.color, part.hasSourceColors], ["box", "#a4abb3", true]);
});

test("a visual's colour is the description's, else its mesh's own, else none: the viewer's surface colour applies", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [{ name: "base_link", visuals: [
      { id: "base_link:painted", label: "painted", partFileRef: "painted-part", color: "#2b2f33", localTransform: translationTransform(0, 0, 0) },
      { id: "base_link:source", label: "source", partFileRef: "source-part", localTransform: translationTransform(0, 0, 0) },
      { id: "base_link:default", label: "default", occurrenceId: "o1.2.10", partFileRef: "default-part", localTransform: translationTransform(0, 0, 0) }
    ] }],
    joints: []
  };
  const meshes = new Map([
    ["painted-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] }, [0.8, 0.1, 0.1])],
    ["source-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] }, [0.25, 0.5, 0.75])],
    ["default-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })]
  ]);

  const parts = buildUrdfVisualParts(urdfData, meshes);

  assert.deepEqual(parts.map((part) => part.color), ["#2b2f33", "", ""]);
  assert.deepEqual(parts.map((part) => part.hasSourceColors), [true, true, false]);
  assert.deepEqual(Array.from(parts[1].sourceMesh.colors.slice(0, 3)), [0.25, 0.5, 0.75], "the mesh's own colours travel with it");
  assert.equal(parts[2].occurrenceId, "o1.2.10");
});

test("a visual whose mesh did not load has no part", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [{ name: "base_link", visuals: [{ id: "base_link:lost", partFileRef: "lost-part", localTransform: translationTransform(0, 0, 0) }] }],
    joints: []
  };
  assert.deepEqual(buildUrdfVisualParts(urdfData, new Map()), []);
});

// A link mesh whose colour is PER PART rather than per vertex — a GLB with one material per
// primitive is the ordinary case. `has_source_colors` is true, the `colors` buffer is empty,
// and the colour sits on `parts[].color`. The composer only read the buffer, so an authored
// two-colour mesh rendered as one grey link with nothing said about it.
function multiMaterialPartMesh() {
  const vertices = new Float32Array([
    0, 0, 0, 1, 0, 0, 0, 1, 0,
    2, 0, 0, 3, 0, 0, 2, 1, 0
  ]);
  return {
    vertices,
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    bounds: { min: [0, 0, 0], max: [3, 1, 0] },
    colors: new Float32Array(0),
    has_source_colors: true,
    parts: [
      { name: "shell", color: "#e4572e", vertexOffset: 0, vertexCount: 3 },
      { name: "cap", color: "#17bebb", vertexOffset: 3, vertexCount: 3 }
    ]
  };
}

function multiMaterialUrdf() {
  return {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:hand",
            label: "hand",
            partFileRef: "hand-part",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };
}

test("a link mesh coloured by material carries its colours per vertex, so its part is a coloured one", () => {
  const meshes = new Map([["hand-part", multiMaterialPartMesh()]]);

  const [part] = buildUrdfVisualParts(multiMaterialUrdf(), meshes);

  assert.equal(part.hasSourceColors, true);
  assert.equal(part.sourceMesh.colors.length, part.sourceMesh.vertices.length,
    "the part the scene draws from carries a full colour buffer");
  assert.deepEqual(rounded(part.sourceMesh.colors.slice(0, 9)), rounded(repeatedTriplet(linearHexTriplet("#e4572e"))),
    "the first primitive keeps its own material colour");
  assert.deepEqual(rounded(part.sourceMesh.colors.slice(9, 18)), rounded(repeatedTriplet(linearHexTriplet("#17bebb"))),
    "and so does the second");
});

test("a URDF <material> is the part's colour over the mesh's own materials", () => {
  const urdfData = multiMaterialUrdf();
  urdfData.links[0].visuals[0].color = "#2b2f33";
  const meshes = new Map([["hand-part", multiMaterialPartMesh()]]);

  const [part] = buildUrdfVisualParts(urdfData, meshes);

  assert.deepEqual([part.color, part.hasSourceColors], ["#2b2f33", true]);
});
