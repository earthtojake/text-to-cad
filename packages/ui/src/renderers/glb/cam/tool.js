/**
 * The tool that rides a CAM result's path while it plays, its tip on the path, sized in mm so it reads at the
 * scale of the part, built once per shape and swapped as the program changes tools: a cylinder (a ball on a
 * cylinder for a ball end mill) under a wider holder, sized from the operation's tool (`toolDiameterMm`), standing
 * along its setup's axis (the direction its tool comes from, +Z or -Z). A path naming an operation or a setup the job
 * does not list is no result cadgen wrote: refused (`CamResultError`), never drawn as some other tool.
 */

import { CamResultError } from "./extras.js";

const COLOURS = Object.freeze({ cutter: "#a1a1aa", holder: "#52525b" });

/** What the tool is drawn as for an operation (`readCamJob`'s): `{ radius (mm), ball }`. */
export function toolShape(op) {
  return { radius: op.toolDiameterMm / 2, ball: op.toolType === "ball" };
}

/**
 * @param {typeof import("three")} THREE
 * @param {import("three").Object3D} root  Where the paths are drawn (`createCamPaths`'s parent, in the scene root's frame),
 *   the tool beside them.
 * @param {object} job  `readCamJob`.
 * @param {{ mmPerUnit: number, direction(vector: number[]): import("three").Vector3 }} frame  `cadFrame`.
 */
export function createCamTool(THREE, root, job, frame) {
  const group = new THREE.Group();
  group.name = "cam-tool";
  group.visible = false;
  group.userData.camDrawn = true;
  group.raycast = () => {};
  root.add(group);
  const unit = 1 / (frame.mmPerUnit || 1);
  const materials = {
    cutter: new THREE.MeshStandardMaterial({ color: COLOURS.cutter, metalness: 0.6, roughness: 0.35 }),
    holder: new THREE.MeshStandardMaterial({ color: COLOURS.holder, metalness: 0.4, roughness: 0.5 }),
  };
  const built = new Map();
  const up = new THREE.Vector3(0, 1, 0);
  const setups = new Map(job.setups.map((setup) => [setup.id, setup]));

  // One tool, its tip at the origin and its axis up +Y: the cutter (a ball end's sphere at its tip), then the holder.
  const build = ({ radius, ball }) => {
    const key = `${radius}:${ball}`;
    if (built.has(key)) return built.get(key);
    const tool = new THREE.Group();
    const flute = Math.max(radius * 6, 6);
    const shaft = flute - (ball ? radius : 0);
    tool.add(new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, shaft, 24).translate(0, flute - shaft / 2, 0), materials.cutter));
    if (ball) tool.add(new THREE.Mesh(new THREE.SphereGeometry(radius, 24, 12).translate(0, radius, 0), materials.cutter));
    const holderRadius = Math.max(radius * 2, radius + 4);
    const holderHeight = Math.max(holderRadius * 2.5, 16);
    tool.add(new THREE.Mesh(new THREE.CylinderGeometry(holderRadius, holderRadius, holderHeight, 32).translate(0, flute + holderHeight / 2, 0), materials.holder));
    tool.scale.setScalar(unit);
    tool.traverse((object) => { object.raycast = () => {}; object.userData.camDrawn = true; });
    built.set(key, tool);
    return tool;
  };

  let shown = null;
  return {
    object3D: group,
    /** Stands the tool of the operation at `place.op` with its tip on `place.point` (the root's frame), along its setup's axis; or hides it. */
    show(place) {
      if (!place) { group.visible = false; return; }
      const op = job.operations.find((entry) => entry.index === place.op);
      if (!op) throw new CamResultError(`a toolpath's _CAM_OP ${place.op}`, "names an operation the result does not list");
      const tool = build(toolShape(op));
      if (shown !== tool) {
        if (shown) group.remove(shown);
        group.add(tool);
        shown = tool;
      }
      const setup = setups.get(place.setup);
      if (!setup) throw new CamResultError(`a toolpath's setup ${place.setup}`, "names a setup the result does not list");
      group.quaternion.setFromUnitVectors(up, frame.direction(setup.axis));
      group.position.fromArray(place.point);
      group.visible = true;
    },
    hide() { group.visible = false; },
    dispose() {
      group.removeFromParent();
      for (const tool of built.values()) tool.traverse((object) => object.geometry?.dispose());
      built.clear();
      for (const material of Object.values(materials)) material.dispose();
    },
  };
}
