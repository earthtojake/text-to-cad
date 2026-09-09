import assert from "node:assert/strict";
import test from "node:test";

import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry,
  buildUrdfMeshData,
  clampJointValueDeg,
  linkOriginInFrame,
  poseUrdfMeshData,
  posedJointLocalTransform,
  rootPointInFrame,
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

const PART_MESHES = new Map([
  ["base-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })],
  ["arm-part", partMesh({ min: [0, 0, 0], max: [2, 1, 0] })],
  ["tool-part", partMesh({ min: [0, 0, 0], max: [1, 2, 0] })]
]);

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

test("root-frame points can be expressed in another link frame", () => {
  const urdf = sampleUrdf();

  assert.deepEqual(
    rounded(rootPointInFrame(urdf, { base_to_arm: 0 }, [10, 6, 0], "arm_link")),
    [0, 6, 0]
  );
  assert.deepEqual(
    rounded(rootPointInFrame(urdf, { base_to_arm: 90 }, [5, 0, 0], "arm_link")),
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

test("posed mesh bounds update after joint motion", () => {
  const zeroPose = buildUrdfMeshData(sampleUrdf(), PART_MESHES, { base_to_arm: 0 });
  const rotatedPose = buildUrdfMeshData(sampleUrdf(), PART_MESHES, { base_to_arm: 90 });

  assert.notDeepEqual(zeroPose.meshData.bounds, rotatedPose.meshData.bounds);
  assert.equal(zeroPose.meshData.parts.length, 3);
  assert.equal(rotatedPose.meshData.parts.length, 3);
});

test("posing URDF mesh data reuses the static geometry buffers", () => {
  const meshGeometry = buildUrdfMeshGeometry(sampleUrdf(), PART_MESHES);
  const zeroPose = poseUrdfMeshData(sampleUrdf(), meshGeometry, { base_to_arm: 0 });
  const rotatedPose = poseUrdfMeshData(sampleUrdf(), meshGeometry, { base_to_arm: 90 });

  assert.equal(zeroPose.meshData.vertices, meshGeometry.vertices);
  assert.equal(rotatedPose.meshData.vertices, meshGeometry.vertices);
  assert.equal(zeroPose.meshData.indices, meshGeometry.indices);
  assert.equal(rotatedPose.meshData.indices, meshGeometry.indices);
  assert.equal(zeroPose.meshData.geometrySource, meshGeometry);
  assert.equal(rotatedPose.meshData.geometrySource, meshGeometry);
  assert.notDeepEqual(zeroPose.meshData.bounds, rotatedPose.meshData.bounds);
});

test("applying a URDF pose in place preserves mesh identity and updates posed parts", () => {
  const meshGeometry = buildUrdfMeshGeometry(sampleUrdf(), PART_MESHES);
  const zeroPose = applyUrdfPoseToMeshData(sampleUrdf(), meshGeometry, { base_to_arm: 0 });
  const zeroParts = zeroPose.meshData.parts;
  const zeroBounds = zeroPose.meshData.bounds;
  const rotatedPose = applyUrdfPoseToMeshData(sampleUrdf(), meshGeometry, { base_to_arm: 90 });

  assert.equal(zeroPose.meshData, meshGeometry);
  assert.equal(rotatedPose.meshData, meshGeometry);
  assert.equal(rotatedPose.meshData.geometrySource, meshGeometry);
  assert.notEqual(rotatedPose.meshData.parts, zeroParts);
  assert.notDeepEqual(zeroBounds, rotatedPose.meshData.bounds);
  assert.notDeepEqual(
    zeroParts.find((part) => part.linkName === "arm_link").transform,
    rotatedPose.meshData.parts.find((part) => part.linkName === "arm_link").transform
  );
});

test("posed URDF mesh data can override link world transforms", () => {
  const meshGeometry = buildUrdfMeshGeometry(sampleUrdf(), PART_MESHES);
  const overrideTransform = translationTransform(25, 0, 0);
  const posed = poseUrdfMeshData(
    sampleUrdf(),
    meshGeometry,
    { base_to_arm: 0 },
    new Map([["arm_link", overrideTransform]])
  );

  assert.deepEqual(transformPoint(posed.linkWorldTransforms.get("arm_link"), [0, 0, 0]), [25, 0, 0]);
  assert.deepEqual(transformPoint(posed.meshData.parts.find((part) => part.linkName === "arm_link").transform, [0, 0, 0]), [25, 0, 0]);
});

test("posed URDF mesh data preserves resolved visual colors", () => {
  const posed = buildUrdfMeshData(sampleUrdf(), PART_MESHES, { base_to_arm: 0 });

  assert.deepEqual(
    posed.meshData.parts.map((part) => part.color),
    ["#2b2f33", "#a4abb3", "#a4abb3"]
  );
  assert.equal(posed.meshData.has_source_colors, true);
  assert.deepEqual(
    rounded(posed.meshData.colors.slice(0, 9)),
    rounded(repeatedTriplet(linearHexTriplet("#2b2f33")))
  );
  assert.deepEqual(
    rounded(posed.meshData.colors.slice(9, 18)),
    rounded(repeatedTriplet(linearHexTriplet("#a4abb3")))
  );
});

test("URDF mesh data builds primitive box visuals without external mesh assets", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:v1",
            label: "box",
            primitive: {
              type: "box",
              size: [2, 4, 6]
            },
            color: "#a4abb3",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };

  const meshGeometry = buildUrdfMeshGeometry(urdfData, new Map());

  assert.equal(meshGeometry.parts.length, 1);
  assert.equal(meshGeometry.parts[0].vertexCount, 24);
  assert.equal(meshGeometry.parts[0].triangleCount, 12);
  assert.deepEqual(meshGeometry.parts[0].bounds, {
    min: [-1, -2, -3],
    max: [1, 2, 3]
  });
  assert.equal(meshGeometry.has_source_colors, true);
  assert.deepEqual(
    rounded(meshGeometry.colors.slice(0, 9)),
    rounded(repeatedTriplet(linearHexTriplet("#a4abb3")))
  );
});

test("URDF mesh data preserves mesh source colors when visuals omit material colors", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:painted",
            label: "painted",
            partFileRef: "painted-part",
            color: "#2b2f33",
            localTransform: translationTransform(0, 0, 0)
          },
          {
            id: "base_link:source",
            label: "source",
            partFileRef: "source-part",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };
  const meshes = new Map([
    ["painted-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] }, [0.8, 0.1, 0.1])],
    ["source-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] }, [0.25, 0.5, 0.75])]
  ]);

  const meshGeometry = buildUrdfMeshGeometry(urdfData, meshes);

  assert.equal(meshGeometry.has_source_colors, true);
  assert.deepEqual(
    meshGeometry.parts.map((part) => part.color),
    ["#2b2f33", ""]
  );
  assert.deepEqual(
    rounded(meshGeometry.colors.slice(0, 9)),
    rounded(repeatedTriplet(linearHexTriplet("#2b2f33")))
  );
  assert.deepEqual(
    Array.from(meshGeometry.colors.slice(9, 18)),
    [0.25, 0.5, 0.75, 0.25, 0.5, 0.75, 0.25, 0.5, 0.75]
  );
});

test("URDF mesh data marks uncolored visuals for default viewer color", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:motor",
            label: "motor",
            partFileRef: "motor-part",
            color: "#2b2f33",
            localTransform: translationTransform(0, 0, 0)
          },
          {
            id: "base_link:default",
            label: "default",
            partFileRef: "default-part",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };
  const meshes = new Map([
    ["motor-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })],
    ["default-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })]
  ]);

  const meshGeometry = buildUrdfMeshGeometry(urdfData, meshes);

  assert.equal(meshGeometry.has_source_colors, true);
  assert.deepEqual(
    meshGeometry.parts.map((part) => part.hasSourceColors),
    [true, false]
  );
  assert.deepEqual(
    rounded(meshGeometry.colors.slice(0, 9)),
    rounded(repeatedTriplet(linearHexTriplet("#2b2f33")))
  );
  assert.deepEqual(Array.from(meshGeometry.colors.slice(9, 18)), [1, 1, 1, 1, 1, 1, 1, 1, 1]);
});

test("URDF mesh geometry can keep source meshes for lightweight viewer rendering", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:first",
            label: "first",
            partFileRef: "shared-part",
            localTransform: translationTransform(0, 0, 0)
          },
          {
            id: "base_link:second",
            label: "second",
            partFileRef: "shared-part",
            localTransform: translationTransform(2, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };
  const sharedMesh = partMesh({ min: [0, 0, 0], max: [1, 1, 0] });
  const meshes = new Map([["shared-part", sharedMesh]]);

  const meshGeometry = buildUrdfMeshGeometry(urdfData, meshes, { lightweight: true });
  const posed = poseUrdfMeshData(urdfData, meshGeometry, {});

  assert.equal(meshGeometry.lightweightGeometry, true);
  assert.equal(meshGeometry.parts[0].sourceMesh, sharedMesh);
  assert.equal(meshGeometry.parts[1].sourceMesh, sharedMesh);
  assert.equal(meshGeometry.vertices.length, 9);
  assert.equal(meshGeometry.indices.length, 3);
  assert.deepEqual(posed.meshData.bounds, {
    min: [0, 0, 0],
    max: [3, 1, 0]
  });
});

test("URDF mesh data leaves uncolored robots for theme fill colors", () => {
  const urdfData = {
    rootLink: "base_link",
    rootWorldTransform: translationTransform(0, 0, 0),
    links: [
      {
        name: "base_link",
        visuals: [
          {
            id: "base_link:first",
            label: "first",
            occurrenceId: "o1.2.10",
            partFileRef: "first-part",
            localTransform: translationTransform(0, 0, 0)
          },
          {
            id: "base_link:second",
            label: "second",
            occurrenceId: "o1.2.11",
            partFileRef: "second-part",
            localTransform: translationTransform(0, 0, 0)
          }
        ]
      }
    ],
    joints: []
  };
  const meshes = new Map([
    ["first-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })],
    ["second-part", partMesh({ min: [0, 0, 0], max: [1, 1, 0] })]
  ]);

  const meshGeometry = buildUrdfMeshGeometry(urdfData, meshes);

  assert.equal(meshGeometry.has_source_colors, false);
  assert.deepEqual(
    meshGeometry.parts.map((part) => part.color),
    ["", ""]
  );
  assert.deepEqual(
    meshGeometry.parts.map((part) => part.hasSourceColors),
    [false, false]
  );
  assert.deepEqual(
    meshGeometry.parts.map((part) => part.occurrenceId),
    ["o1.2.10", "o1.2.11"]
  );
  assert.equal(meshGeometry.colors.length, 0);
});
