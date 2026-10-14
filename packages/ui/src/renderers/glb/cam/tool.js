/**
 * The tool that rides a CAM result's path while it plays, its tip on the path, sized in mm so it reads at the
 * scale of the part, built once per shape and swapped as the program changes tools. What it looks like follows
 * the machine:
 *
 * - a mill's (and a lathe's) cutter: a cylinder, or a ball on a cylinder for a ball end mill, under a wider holder,
 *   sized from the operation's tool (`toolDiameterMm`; 6 mm when the file does not say);
 * - a laser's, plasma's or waterjet's head: a nozzle over its tip and the beam (its kerf wide) down through the sheet;
 * - a wire EDM's wire: the wire through the work between its two guides.
 *
 * Which way it stands: the tool's own axis where the file carries one per vertex (a rotary wrap, swarf, a 5-axis
 * finish, a tapered wire), else its setup's (the direction its tool comes from: the setup's `axis`, from the
 * extras' `matrix`, so a 3+2 setup's tilt too); a lathe's turning tools come in across the spindle (the setup's
 * `across`) and its drill along it.
 */

const DEFAULT_RADIUS_MM = 3;
const COLOURS = Object.freeze({ cutter: "#a1a1aa", holder: "#52525b", beam: "#f97316", wire: "#ca8a04" });
const CUTTING = new Set(["laser", "plasma", "waterjet"]);
// A setup's orientation as the job writes it, for a setup the reader gave no axis.
const AXES = Object.freeze({ "+Z": [0, 0, 1], "-Z": [0, 0, -1], "+X": [1, 0, 0], "-X": [-1, 0, 0], "+Y": [0, 1, 0], "-Y": [0, -1, 0] });

/** The axis a setup's tool stands along, in CAD space: its `axis` (`readCamJob`), else its orientation's, else +Z. */
export const setupAxis = (setup) => (Array.isArray(setup?.axis) && setup.axis.length === 3 ? setup.axis
  : AXES[String(setup?.orientation || "").toUpperCase()] || AXES["+Z"]);

/** The axis an operation's tool stands along, in CAD space: a lathe's turning tools across the spindle. */
export function operationAxis(job, setup, op) {
  if (job?.machine === "lathe" && op?.op !== "turn_drill" && Array.isArray(setup?.across)) return setup.across;
  return setupAxis(setup);
}

/** What the tool is drawn as for an operation: `{ kind: "cutter" | "beam" | "wire", radius (mm), ball }`. */
export function toolShape(job, op) {
  if (job?.machine === "wire_edm") return { kind: "wire", radius: Math.max((op?.toolDiameterMm || 0.25) / 2, 0.15), ball: false };
  if (CUTTING.has(job?.machine)) return { kind: "beam", radius: Math.max((op?.kerfMm || 0.3) / 2, 0.15), ball: false };
  return { kind: "cutter", radius: op?.toolDiameterMm > 0 ? op.toolDiameterMm / 2 : DEFAULT_RADIUS_MM, ball: op?.toolType === "ball" };
}

/**
 * @param {typeof import("three")} THREE
 * @param {import("three").Object3D} root  Where the paths are drawn (`createCamPaths`), the tool beside them.
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
    beam: new THREE.MeshStandardMaterial({ color: COLOURS.beam, emissive: COLOURS.beam, emissiveIntensity: 0.6, roughness: 0.8 }),
    wire: new THREE.MeshStandardMaterial({ color: COLOURS.wire, metalness: 0.7, roughness: 0.3 }),
  };
  const built = new Map();
  const up = new THREE.Vector3(0, 1, 0);
  const axis = new THREE.Vector3();
  const setups = new Map(job.setups.map((setup) => [setup.id, setup]));
  // The work's height for a beam or a wire to pass through (a sheet's thickness), 3 mm when the file does not say.
  const thickness = job.stock?.thicknessMm > 0 ? job.stock.thicknessMm : 3;

  const cylinder = (radius, from, to, material, segments = 24) => new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, to - from, segments).translate(0, (from + to) / 2, 0), material);

  // One tool, its tip at the origin and its axis up +Y.
  const build = (shape) => {
    const key = `${shape.kind}:${shape.radius}:${shape.ball}`;
    if (built.has(key)) return built.get(key);
    const tool = new THREE.Group();
    const { radius } = shape;
    if (shape.kind === "wire") {
      // The tip is the program plane (the work's top): the wire runs down through the work to the lower guide.
      tool.add(cylinder(radius, -thickness - 4, 4, materials.wire, 12));
      tool.add(cylinder(3, 4, 7, materials.holder), cylinder(3, -thickness - 7, -thickness - 4, materials.holder));
    } else if (shape.kind === "beam") {
      // The tip is the head over the sheet: a nozzle above it and the beam down through the sheet.
      tool.add(cylinder(radius, -thickness - 6, 0, materials.beam, 12));
      tool.add(new THREE.Mesh(new THREE.CylinderGeometry(4, 1, 8, 24).translate(0, 4, 0), materials.holder));
      tool.add(cylinder(8, 8, 24, materials.holder, 32));
    } else {
      // The cutter (a ball end's sphere at its tip), then the holder.
      const ball = shape.ball;
      const flute = Math.max(radius * 6, 6);
      const cutter = new THREE.CylinderGeometry(radius, radius, flute - (ball ? radius : 0), 24);
      cutter.translate(0, (ball ? radius : 0) + (flute - (ball ? radius : 0)) / 2, 0);
      tool.add(new THREE.Mesh(cutter, materials.cutter));
      if (ball) tool.add(new THREE.Mesh(new THREE.SphereGeometry(radius, 24, 12).translate(0, radius, 0), materials.cutter));
      const holderRadius = Math.max(radius * 2, radius + 4);
      const holderHeight = Math.max(holderRadius * 2.5, 16);
      tool.add(cylinder(holderRadius, flute, flute + holderHeight, materials.holder, 32));
    }
    tool.scale.setScalar(unit);
    tool.traverse((object) => { object.raycast = () => {}; object.userData.camDrawn = true; });
    built.set(key, tool);
    return tool;
  };

  let shown = null;
  return {
    object3D: group,
    /**
     * Stands the tool of the operation at `place.op` with its tip on `place.point` (the root's frame), along
     * `place.axis` (the root's frame) where the path carries one, else its setup's; or hides it.
     */
    show(place) {
      if (!place) { group.visible = false; return; }
      const op = job.operations.find((entry) => entry.index === place.op) || null;
      const tool = build(toolShape(job, op));
      if (shown !== tool) {
        if (shown) group.remove(shown);
        group.add(tool);
        shown = tool;
      }
      if (Array.isArray(place.axis) && place.axis.length === 3) axis.fromArray(place.axis).normalize();
      else axis.copy(frame.direction(operationAxis(job, setups.get(place.setup || op?.setup), op)));
      group.quaternion.setFromUnitVectors(up, axis);
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
