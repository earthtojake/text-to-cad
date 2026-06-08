import assert from "node:assert/strict";
import test from "node:test";

import { parseUrdf } from "./parseUrdf.js";

class FakeElement {
  constructor(tagName, attributes = {}, children = []) {
    this.nodeType = 1;
    this.tagName = tagName;
    this.localName = String(tagName || "").split(":").pop();
    this.namespaceURI = null;
    this._attributes = { ...attributes };
    this.childNodes = children;
  }

  getAttribute(name) {
    return Object.hasOwn(this._attributes, name) ? this._attributes[name] : null;
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

test("parseUrdf resolves referenced robot material colors from rgba", () => {
  const robot = new FakeElement("robot", { name: "sample_robot" }, [
    new FakeElement("material", { name: "black_aluminum" }, [
      new FakeElement("color", { rgba: "0.168627 0.184314 0.2 1" })
    ]),
    new FakeElement("link", { name: "base_link" }, [
      new FakeElement("visual", {}, [
        new FakeElement("geometry", {}, [
          new FakeElement("mesh", { filename: "meshes/sample_part.stl", scale: "0.001 0.001 0.001" })
        ]),
        new FakeElement("material", { name: "black_aluminum" })
      ])
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", { sourceUrl: "/workspace/sample_robot.urdf" }));

  assert.equal(urdfData.links[0].visuals[0].color, "#2b2f33");
  assert.equal(
    urdfData.links[0].visuals[0].meshUrl,
    "/workspace/meshes/sample_part.stl"
  );
});

test("parseUrdf resolves relative mesh paths through local CAD asset URLs", () => {
  const robot = new FakeElement("robot", { name: "sample_robot" }, [
    new FakeElement("link", { name: "base_link" }, [
      new FakeElement("visual", {}, [
        new FakeElement("geometry", {}, [
          new FakeElement("mesh", { filename: "meshes/sample_part.stl" })
        ])
      ])
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", {
    sourceUrl: "/__cad/asset?file=%2Fworkspace%2Frobots%2Fsample_robot.urdf&v=abc123"
  }));

  assert.equal(
    urdfData.links[0].visuals[0].meshUrl,
    "/__cad/asset?file=%2Fworkspace%2Frobots%2Fmeshes%2Fsample_part.stl"
  );
});

test("parseUrdf preserves remote origins when resolving hosted mesh paths", () => {
  const robot = new FakeElement("robot", { name: "tom" }, [
    new FakeElement("link", { name: "base_link" }, [
      new FakeElement("visual", {}, [
        new FakeElement("geometry", {}, [
          new FakeElement("mesh", { filename: "STL/sts3250.stl" })
        ])
      ]),
      new FakeElement("visual", {}, [
        new FakeElement("geometry", {}, [
          new FakeElement("mesh", { filename: "https://cdn.example.test/meshes/tool.stl" })
        ])
      ])
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", {
    sourceUrl: "https://blob.example.test/models2/robots/tom/robot_arm.urdf"
  }));

  assert.equal(
    urdfData.links[0].visuals[0].meshUrl,
    "https://blob.example.test/models2/robots/tom/STL/sts3250.stl"
  );
  assert.equal(
    urdfData.links[0].visuals[1].meshUrl,
    "https://cdn.example.test/meshes/tool.stl"
  );
});

test("parseUrdf accepts primitive box visuals", () => {
  const robot = new FakeElement("robot", { name: "primitive_robot" }, [
    new FakeElement("material", { name: "aluminum" }, [
      new FakeElement("color", { rgba: "0.72 0.78 0.82 1" })
    ]),
    new FakeElement("link", { name: "base_link" }, [
      new FakeElement("visual", {}, [
        new FakeElement("origin", { xyz: "0.025 0 0.003", rpy: "0 0 0" }),
        new FakeElement("geometry", {}, [
          new FakeElement("box", { size: "0.17 0.13 0.006" })
        ]),
        new FakeElement("material", { name: "aluminum" })
      ])
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", { sourceUrl: "/workspace/primitive_robot.urdf" }));

  assert.deepEqual(urdfData.links[0].visuals[0].primitive, {
    type: "box",
    size: [0.17, 0.13, 0.006]
  });
  assert.equal(urdfData.links[0].visuals[0].meshUrl, undefined);
  assert.equal(urdfData.links[0].visuals[0].color, "#b8c7d1");
});

test("parseUrdf ignores custom default_deg joint attributes", () => {
  const robot = new FakeElement("robot", { name: "sample_robot" }, [
    new FakeElement("link", { name: "base_link" }),
    new FakeElement("link", { name: "arm_link" }),
    new FakeElement("joint", { name: "base_to_arm", type: "continuous", default_deg: "90" }, [
      new FakeElement("parent", { link: "base_link" }),
      new FakeElement("child", { link: "arm_link" }),
      new FakeElement("origin", { xyz: "0 0 0", rpy: "0 0 0" }),
      new FakeElement("axis", { xyz: "0 1 0" })
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", { sourceUrl: "/workspace/sample_robot.urdf" }));

  assert.equal(urdfData.joints[0].defaultValueDeg, 0);
  assert.equal(urdfData.motion, null);
  assert.equal(urdfData.srdf, null);
});

test("parseUrdf accepts prismatic mimic joints", () => {
  const robot = new FakeElement("robot", { name: "sample_robot" }, [
    new FakeElement("link", { name: "base_link" }),
    new FakeElement("link", { name: "driver_link" }),
    new FakeElement("link", { name: "slider_link" }),
    new FakeElement("joint", { name: "driver_joint", type: "revolute" }, [
      new FakeElement("parent", { link: "base_link" }),
      new FakeElement("child", { link: "driver_link" }),
      new FakeElement("limit", { lower: "0", upper: "1", effort: "1", velocity: "1" })
    ]),
    new FakeElement("joint", { name: "slider_joint", type: "prismatic" }, [
      new FakeElement("parent", { link: "base_link" }),
      new FakeElement("child", { link: "slider_link" }),
      new FakeElement("axis", { xyz: "1 0 0" }),
      new FakeElement("limit", { lower: "0", upper: "0.05", effort: "1", velocity: "1" }),
      new FakeElement("mimic", { joint: "driver_joint", multiplier: "0.0065", offset: "0" })
    ])
  ]);

  const urdfData = withFakeDomParser(new FakeDocument(robot), () => parseUrdf("<robot />", { sourceUrl: "/workspace/sample_robot.urdf" }));

  assert.equal(urdfData.joints[1].type, "prismatic");
  assert.equal(urdfData.joints[1].maxValueDeg, 0.05);
  assert.deepEqual(urdfData.joints[1].mimic, {
    joint: "driver_joint",
    multiplier: 0.0065,
    offset: 0
  });
});
