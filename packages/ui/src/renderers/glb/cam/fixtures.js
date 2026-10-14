/**
 * What holds the part in each setup, drawn as the job's keep-out boxes (`setups[].fixtures`, part coordinates in mm):
 * see-through steel, matte and never shiny, so the part standing in it reads apart from it. Only the boxes of the
 * setup the view is about are up: while a clip plays, the setup under way; while a row is chosen, its operations'
 * setups; else the first setup's that has any.
 */

/** How a fixture is drawn in each scheme: a cool steel blue, see-through. */
export const FIXTURE_LOOK = Object.freeze({
  light: Object.freeze({ colour: "#4f6a8f", opacity: 0.2 }),
  dark: Object.freeze({ colour: "#7d93b0", opacity: 0.28 }),
});

/** Whether the job has a fixture box to draw. */
export const camHasFixtures = (job) => Boolean(job?.setups.some((setup) => setup.fixtures?.length));

/**
 * Which setups' fixtures are up: the setup a moment plays (`setup` the tool's place names, else the clip's), the
 * setups of the operations chosen (`isolate`), else the first setup that has fixtures (null when none has).
 */
export function fixtureSetups(job, { isolate = null, moment = null, playing = null } = {}) {
  if (moment) {
    const setup = playing || moment.setup;
    return setup ? new Set([setup]) : null;
  }
  if (isolate?.size) return new Set(job.operations.filter((op) => isolate.has(op.index)).map((op) => op.setup));
  // At rest, the first setup that has fixtures: each setup holds the part its own way, and two setups' vises drawn
  // round one part at once would show a hold no setup has.
  const first = job.setups.find((setup) => setup.fixtures?.length);
  return first ? new Set([first.id]) : null;
}

/**
 * @param {typeof import("three")} THREE
 * @param {import("three").Object3D} root  Where the paths are drawn, the boxes beside them.
 * @param {object} job  `readCamJob`.
 * @param {{ toLocal: import("three").Matrix4 }} frame  `cadFrame`: CAD space (mm) to the root's frame.
 * @returns {{ object3D: import("three").Group, count: number, style(scheme: string): void,
 *   update(options: { shown?: boolean, setups?: Set<string> | null }): boolean, dispose(): void }}
 */
export function createCamFixtures(THREE, root, job, frame, scheme = "light") {
  const group = new THREE.Group();
  group.name = "cam-fixtures";
  group.userData.camDrawn = true;
  group.raycast = () => {};
  const material = new THREE.MeshStandardMaterial({ metalness: 0, roughness: 0.9, transparent: true, depthWrite: false });
  const boxes = [];
  const centre = new THREE.Vector3();
  for (const setup of job.setups) {
    for (const fixture of setup.fixtures || []) {
      const size = fixture.max.map((value, axis) => Math.max(value - fixture.min[axis], 1e-3));
      const geometry = new THREE.BoxGeometry(...size);
      const mesh = new THREE.Mesh(geometry, material);
      centre.fromArray(fixture.min.map((value, axis) => (value + fixture.max[axis]) / 2));
      // The box in CAD space, then CAD space to the root's frame, whatever turns and scales that.
      mesh.matrixAutoUpdate = false;
      mesh.matrix.copy(frame.toLocal).multiply(new THREE.Matrix4().makeTranslation(centre.x, centre.y, centre.z));
      mesh.name = `cam-fixture-${setup.id}-${fixture.name}`;
      mesh.renderOrder = 1;
      mesh.raycast = () => {};
      mesh.userData.camDrawn = true;
      mesh.userData.setup = setup.id;
      group.add(mesh);
      boxes.push({ mesh, setup: setup.id });
    }
  }
  root.add(group);
  const style = (next) => {
    const look = FIXTURE_LOOK[next === "dark" ? "dark" : "light"];
    material.color.set(look.colour);
    material.opacity = look.opacity;
    material.needsUpdate = true;
  };
  style(scheme);
  return {
    object3D: group,
    get count() { return boxes.length; },
    style,
    /** Shows the boxes of `setups` (null: every setup's) while `shown`. Returns whether anything changed. */
    update({ shown = true, setups = null } = {}) {
      let changed = false;
      for (const { mesh, setup } of boxes) {
        const visible = shown && (!setups || setups.has(setup));
        if (mesh.visible !== visible) { mesh.visible = visible; changed = true; }
      }
      return changed;
    },
    dispose() {
      group.removeFromParent();
      for (const { mesh } of boxes) mesh.geometry.dispose();
      boxes.length = 0;
      material.dispose();
    },
  };
}
