import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRobotComponentGeometry,
  robotComponentReference,
  robotComponents
} from "./robotComponents.js";

// A visual whose loaded mesh carries `count` named objects laid out back to back, each a
// single triangle. The shape mirrors what the mesh loaders hand the URDF geometry builder.
function visualWithObjects(id, linkName, objects) {
  const vertices = [];
  const indices = [];
  for (let index = 0; index < objects.length; index += 1) {
    const base = index * 3;
    vertices.push(base, 0, 0, base + 1, 0, 0, base, 1, 0);
    indices.push(base, base + 1, base + 2);
  }
  return {
    id,
    name: id,
    linkName,
    meshUrl: `${linkName}.3mf`,
    sourceMeshKey: `${id}#mesh`,
    sourceMesh: {
      vertices: Float32Array.from(vertices),
      normals: Float32Array.from(vertices.map(() => 0)),
      indices: Uint32Array.from(indices),
      parts: objects.map((object, index) => ({
        id: object.id ?? `3mf:${index}`,
        name: object.name,
        vertexOffset: index * 3,
        vertexCount: 3,
        triangleOffset: index,
        triangleCount: 1,
        bounds: null,
        ...object.overrides
      }))
    }
  };
}

test("named mesh objects become one pickable part each", () => {
  const meshData = {
    parts: [visualWithObjects("arm:v1", "arm", [{ name: "bracket" }, { name: "pulley" }])]
  };
  const split = buildRobotComponentGeometry(meshData);
  assert.equal(split.parts.length, 2);
  assert.deepEqual(split.parts.map((part) => part.componentName), ["bracket", "pulley"]);
  assert.deepEqual(split.parts.map((part) => part.id), ["arm:v1/object/0", "arm:v1/object/1"]);
  // Each slice is rebased onto its own vertices rather than pointing into the whole mesh.
  assert.deepEqual([...split.parts[1].sourceMesh.indices], [0, 1, 2]);
  assert.equal(split.parts[1].sourceMesh.vertices.length, 9);
  // The visual's identity survives the split, so a component still names its link.
  assert.equal(split.parts[1].linkName, "arm");
  assert.equal(split.parts[1].visualId, "arm:v1");
});

test("a visual with no named objects is left whole", () => {
  const visual = visualWithObjects("base:v1", "base", [{ name: "" }, { name: "Unnamed component" }]);
  const split = buildRobotComponentGeometry({ parts: [visual] });
  assert.deepEqual(split.parts, [visual]);
  assert.deepEqual(robotComponents(split, "robot.urdf"), []);
});

test("an unsliceable object costs its visual's components, never the robot's geometry", () => {
  // BLOCKING: this used to throw, and the throw was caught where the whole robot's
  // geometry is built — so one bad part from a loader blanked the entire render.
  const warnings = [];
  const realWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    for (const overrides of [
      { vertexCount: -1 },
      { vertexCount: 0 },
      { triangleCount: undefined },
      { vertexOffset: 1.5 },
      { triangleOffset: 9000 },
      { vertexOffset: 9000 },
      // Ranges that fit the buffers, but whose triangles index outside the object.
      { vertexOffset: 0, vertexCount: 3, triangleOffset: 1, triangleCount: 1 }
    ]) {
      const broken = visualWithObjects("arm:v1", "arm", [
        { name: "bracket", overrides },
        { name: "pulley" }
      ]);
      const good = visualWithObjects("base:v1", "base", [{ name: "foot" }]);
      const split = buildRobotComponentGeometry({ parts: [broken, good] });

      // The bad visual renders exactly as it did before the split existed...
      assert.deepEqual(split.parts[0], broken, `visual kept whole for ${JSON.stringify(overrides)}`);
      // ...and contributes no component rows, while its healthy sibling still does.
      const components = robotComponents(split, "robot.urdf");
      assert.deepEqual(components.map((component) => component.name), ["foot"]);
    }
  } finally {
    console.warn = realWarn;
  }
  assert.ok(warnings.length > 0, "an invalid part is reported");
  assert.ok(
    warnings.every((line) => line.includes("Skipping robot mesh object components")),
    "reports through the viewer's console.warn convention"
  );
  // Reported once per distinct part+reason, not once per render.
  assert.equal(new Set(warnings).size, warnings.length);
});

test("buildRobotComponentGeometry passes absent geometry straight through", () => {
  assert.equal(buildRobotComponentGeometry(null), null);
  assert.deepEqual(buildRobotComponentGeometry({ parts: [] }).parts, []);
});

test("a component reference names the file, link, visual and object", () => {
  const meshData = buildRobotComponentGeometry({
    parts: [visualWithObjects("arm:v1", "arm", [{ name: "bracket" }])]
  });
  const [component] = robotComponents(meshData, "models/robot arm.urdf");
  assert.equal(component.name, "bracket");
  assert.equal(component.linkName, "arm");
  assert.equal(component.mesh, "arm.3mf");
  assert.equal(
    component.reference,
    "models/robot%20arm.urdf#link=arm&visual=arm%3Av1&object=3mf%3A0&index=0&name=bracket"
  );
  // Path separators survive; everything else in a segment is percent-encoded.
  assert.equal(
    robotComponentReference("a/b/c.urdf", {
      linkName: "l", visualId: "l:v1", meshObjectId: "0", meshObjectIndex: 0, componentName: "x&y"
    }),
    "a/b/c.urdf#link=l&visual=l%3Av1&object=0&index=0&name=x%26y"
  );
});
