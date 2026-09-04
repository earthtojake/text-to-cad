// Choreography for the Mars rover concept (copied into the sidecar at build;
// the viewer's Animation tab is the only consumer).
//
// Animation knows nothing of the mate graph by design, so the suspension and
// arm chains are re-described here as raw transforms. That is cheap because
// the handle API PREMULTIPLIES: a part turns about its own pivot first, then
// each successive call wraps it in the next link outward, which is forward
// kinematics written parent-last.
//
// Targets are OCCURRENCE IDS rather than labels, because every articulated
// member here is a group (`rocker_left` is a subassembly, not a rendered part)
// and an id ref matches everything beneath it. The table below is the model's
// documented top-level child order — renumber it in the same commit as any
// change to that list.

const REF = {
  terrain: "o1.1",
  chassis: "o1.2",
  bodyCore: "o1.3",
  bodyShell: "o1.4",
  deckLid: "o1.5",
  sidePanelLeft: "o1.6",
  accessPanels: "o1.7",
  thermalControl: "o1.8",
  internalsAvionics: "o1.9",
  internalsPower: "o1.10",
  sciencePayloads: "o1.11",
  cableHarness: "o1.12",
  dustCovers: "o1.13",
  dustLayer: "o1.14",
  rockerLeft: "o1.15",
  rockerRight: "o1.16",
  bogieLeft: "o1.17",
  bogieRight: "o1.18",
  differential: "o1.19",
  steerFrontLeft: "o1.20",
  steerFrontRight: "o1.21",
  steerRearLeft: "o1.22",
  steerRearRight: "o1.23",
  wheelFrontLeft: "o1.24",
  wheelFrontRight: "o1.25",
  wheelMiddleLeft: "o1.26",
  wheelMiddleRight: "o1.27",
  wheelRearLeft: "o1.28",
  wheelRearRight: "o1.29",
  mastBase: "o1.30",
  mastHead: "o1.31",
  armAzimuth: "o1.32",
  armShoulder: "o1.33",
  armElbow: "o1.34",
  armWrist: "o1.35",
  armTurret: "o1.36",
  hgaMast: "o1.37",
  hgaDish: "o1.38",
  antennaUhf: "o1.39",
  antennaWhips: "o1.40",
  solarLeft: "o1.41",
  solarRight: "o1.42",
  rtg: "o1.43"
};

// Everything bolted to the warm body: it rides the chassis bob but has no
// articulation of its own. Terrain is deliberately absent — the ground stays
// put while the rover works over it.
const BODY = [
  REF.chassis, REF.bodyCore, REF.bodyShell, REF.deckLid, REF.sidePanelLeft,
  REF.accessPanels, REF.thermalControl, REF.internalsAvionics, REF.internalsPower,
  REF.sciencePayloads, REF.cableHarness, REF.dustCovers, REF.dustLayer,
  REF.mastBase, REF.mastHead, REF.armAzimuth, REF.armShoulder, REF.armElbow,
  REF.armWrist, REF.armTurret, REF.hgaMast, REF.hgaDish, REF.antennaUhf,
  REF.antennaWhips, REF.solarLeft, REF.solarRight, REF.rtg
].join(",");

const X = [1, 0, 0];
const Y = [0, 1, 0];
const Z = [0, 0, 1];

// Layout constants mirrored from the model's derived layout. Plain numbers,
// because this file is delivered on its own, inlined in the sidecar.
const ROCKER_PIVOT = { left: [150, 760, 800], right: [150, -760, 800] };
const BOGIE_PIVOT = { left: [-700, 760, 430], right: [-700, -760, 430] };
const DIFF_PIVOT = [430, 0, 1235];
const MAST_ORIGIN = [780, -380, 1180];
const HEAD_PIVOT = [780, -380, 2200];
const PANEL_HINGE = [0, 650, 570];
const HGA_PIVOT = [-520, 420, 1360];
const SOLAR_HINGE = { left: [-150, 650, 1186], right: [-150, -650, 1186] };
const ARM_LINKS = [
  { ref: REF.armAzimuth, axis: Z, origin: [1160, 200, 715], key: "azim" },
  { ref: REF.armShoulder, axis: Y, origin: [1160, 200, 760], key: "shoulder" },
  { ref: REF.armElbow, axis: Y, origin: [1761.4, 200, 541.1], key: "elbow" },
  { ref: REF.armWrist, axis: Y, origin: [2268.9, 200, 304.4], key: "wrist" },
  { ref: REF.armTurret, axis: [0.5, 0, -0.866], origin: [2343.9, 200, 174.5], key: "turret" }
];

// Axle center per station, and which suspension member carries it.
const WHEELS = [
  { ref: REF.wheelFrontLeft, center: [1250, 990, 260], side: "left", fork: REF.steerFrontLeft, onBogie: false },
  { ref: REF.wheelFrontRight, center: [1250, -990, 260], side: "right", fork: REF.steerFrontRight, onBogie: false },
  { ref: REF.wheelMiddleLeft, center: [-150, 990, 260], side: "left", fork: null, onBogie: true },
  { ref: REF.wheelMiddleRight, center: [-150, -990, 260], side: "right", fork: null, onBogie: true },
  { ref: REF.wheelRearLeft, center: [-1250, 990, 260], side: "left", fork: REF.steerRearLeft, onBogie: true },
  { ref: REF.wheelRearRight, center: [-1250, -990, 260], side: "right", fork: REF.steerRearRight, onBogie: true }
];

const clamp01 = (u) => Math.min(1, Math.max(0, u));
const ease = {
  sine: (u) => 0.5 - 0.5 * Math.cos(Math.PI * 2 * u),
  smooth: (u) => {
    const c = clamp01(u);
    return c * c * (3 - 2 * c);
  },
  // 0 -> 1 -> 0 across a window of the master ramp
  bump: (u, from, to) => (u <= from || u >= to ? 0 : ease.sine((u - from) / (to - from)))
};

// One frame of the rocker-bogie chain, folded by hand in the same parent order
// the mates declare: wheel -> fork -> bogie -> rocker -> body.
function suspension(m, q) {
  const heave = [0, 0, q.heave];
  const rockerDeg = (side) => (side === "left" ? q.rockerSplit : -q.rockerSplit);

  m.get(BODY).translate(heave);

  for (const side of ["left", "right"]) {
    const rocker = m.get(side === "left" ? REF.rockerLeft : REF.rockerRight);
    rocker.rotate(Y, rockerDeg(side), ROCKER_PIVOT[side]);
    rocker.translate(heave);

    const bogie = m.get(side === "left" ? REF.bogieLeft : REF.bogieRight);
    bogie.rotate(Y, q.bogiePitch, BOGIE_PIVOT[side]);
    bogie.rotate(Y, rockerDeg(side), ROCKER_PIVOT[side]);
    bogie.translate(heave);
  }

  // The differential bar splits the two rockers at half rate.
  const diff = m.get(REF.differential);
  diff.rotate(Z, q.rockerSplit * 0.5, DIFF_PIVOT);
  diff.translate(heave);

  for (const wheel of WHEELS) {
    const { side, fork, onBogie, center } = wheel;
    const steerDeg = fork ? q.steer[fork] || 0 : 0;

    if (fork) {
      const handle = m.get(fork);
      handle.rotate(Z, steerDeg, center);
      if (onBogie) {
        handle.rotate(Y, q.bogiePitch, BOGIE_PIVOT[side]);
      }
      handle.rotate(Y, rockerDeg(side), ROCKER_PIVOT[side]);
      handle.translate(heave);
    }

    const w = m.get(wheel.ref);
    w.rotate(Y, q.drive, center); // its own axle
    w.rotate(Z, steerDeg, center); // the steering fork
    if (onBogie) {
      w.rotate(Y, q.bogiePitch, BOGIE_PIVOT[side]);
    }
    w.rotate(Y, rockerDeg(side), ROCKER_PIVOT[side]);
    w.translate(heave);
  }
}

// The arm chain, folded shoulder-outward. Angles are deltas from the modeled
// sampling hover, so all-zero is the artifact as written.
function armChain(m, q) {
  ARM_LINKS.forEach((link, index) => {
    const handle = m.get(link.ref);
    handle.rotate(link.axis, q[link.key] || 0, link.origin);
    // Each ancestor applied outward is what makes the chain a chain: later
    // calls premultiply, so the parent wraps the child.
    for (let up = index - 1; up >= 0; up -= 1) {
      handle.rotate(ARM_LINKS[up].axis, q[ARM_LINKS[up].key] || 0, ARM_LINKS[up].origin);
    }
  });
}

// Azimuth turns the column, elevation pitches the head on top of it.
function mastScan(m, yawDeg, pitchDeg) {
  m.get(REF.mastBase).rotate(Z, yawDeg, MAST_ORIGIN);
  const head = m.get(REF.mastHead);
  head.rotate(Y, pitchDeg, HEAD_PIVOT);
  head.rotate(Z, yawDeg, MAST_ORIGIN);
}

export const clips = {
  driveAround: {
    label: "Drive-around",
    duration: 18,
    update(t, m) {
      const u = t / 18;
      // Four wheel revolutions a lap, wrapped: 360 reads the same as 0.
      const drive = (u * 4 * 360) % 360;
      const steerDeg = 34 * Math.sin(u * Math.PI * 2 * 2);
      suspension(m, {
        heave: 18 * Math.sin(u * Math.PI * 2 * 10),
        rockerSplit: 6 * Math.sin(u * Math.PI * 2 * 5),
        bogiePitch: 8 * Math.sin(u * Math.PI * 2 * 5 + 1.1),
        drive,
        steer: {
          [REF.steerFrontLeft]: steerDeg,
          [REF.steerFrontRight]: steerDeg * 0.79,
          [REF.steerRearLeft]: -steerDeg,
          [REF.steerRearRight]: -steerDeg * 0.79
        }
      });
      // The mast looks into the turn. It rides the body handle above, so only
      // its own two rotations are described here.
      mastScan(m, -1.6 * steerDeg, 8 * Math.sin(u * Math.PI * 2));
    }
  },

  armCycle: {
    label: "Arm sampling cycle",
    duration: 12,
    update(t, m) {
      const u = t / 12;
      // Reach out, dwell over the target while the turret indexes tools, come
      // back. The dwell is where the drill would be on the rock.
      const reach = ease.bump(u, 0, 0.86);
      armChain(m, {
        azim: -18 * reach,
        shoulder: -30 * reach,
        elbow: 40 * reach,
        wrist: -25 * reach,
        turret: 90 * ease.smooth((u - 0.3) / 0.25) - 90 * ease.smooth((u - 0.62) / 0.2)
      });
      mastScan(m, -14 * reach, 22 * reach);
    }
  },

  deploySequence: {
    label: "Deploy sequence",
    duration: 20,
    update(t, m) {
      const u = t / 20;
      // Staged the way the real thing would come alive: wings out, HGA up,
      // mast raised and panned, arm checked out, deck opened.
      const wings = ease.smooth(u / 0.22);
      const hga = ease.smooth((u - 0.2) / 0.18);
      const mast = ease.smooth((u - 0.36) / 0.18);
      const arm = ease.bump(u, 0.5, 0.78);
      const cutaway = ease.bump(u, 0.74, 1);

      // Wings start folded (-82 deg on the left hinge) and open to the modeled
      // deploy angle, which is this model's zero.
      m.get(REF.solarLeft).rotate(X, -82 * (1 - wings), SOLAR_HINGE.left);
      m.get(REF.solarRight).rotate(X, 82 * (1 - wings), SOLAR_HINGE.right);

      m.get(REF.hgaDish).rotate(Y, -15 + 50 * hga, HGA_PIVOT);

      mastScan(m, 150 * mast * Math.sin(u * Math.PI * 2), -60 * (1 - mast));

      armChain(m, {
        azim: -12 * arm, shoulder: -22 * arm, elbow: 30 * arm,
        wrist: -18 * arm, turret: 180 * arm
      });

      // The deck lid lifts clear and the port panel swings out. The retired
      // pose block also faded the shell and lit the internals here; the handle
      // API has opacity but no emissive, so the dust film thins and the rest
      // of that styling is simply gone.
      m.get(REF.deckLid).translate([0, 0, 420 * cutaway]);
      m.get(REF.sidePanelLeft).rotate(X, -75 * cutaway, PANEL_HINGE);
      m.get(REF.dustLayer).opacity(1 - 0.85 * cutaway);
    }
  },

  explodedAssembly: {
    label: "Exploded assembly",
    duration: 12,
    update(t, m) {
      // The retired `exploded_distance` driver restated: one ramp out and
      // back, each group along its own direction, at the 520 mm peak the old
      // grand tour used.
      const d = ease.sine(t / 12) * 520;
      const vectors = {
        [REF.bodyCore]: [0, 0, 0.35], [REF.bodyShell]: [0, 0, 0.5],
        [REF.deckLid]: [0, 0, 1.15], [REF.sidePanelLeft]: [0, 0.9, 0.15],
        [REF.accessPanels]: [0, -0.8, 0.1], [REF.thermalControl]: [0, -0.35, 0.75],
        [REF.internalsAvionics]: [0, 0, 0.85], [REF.internalsPower]: [0.15, -0.2, 0.75],
        [REF.sciencePayloads]: [-0.2, 0.15, 0.95], [REF.cableHarness]: [0, 0, 0.3],
        [REF.dustCovers]: [0, 0, -0.4], [REF.dustLayer]: [0, 0, 1.35],
        [REF.rockerLeft]: [0, 0.45, 0], [REF.rockerRight]: [0, -0.45, 0],
        [REF.bogieLeft]: [0, 0.6, 0], [REF.bogieRight]: [0, -0.6, 0],
        [REF.differential]: [0, 0, 0.9],
        [REF.steerFrontLeft]: [0.15, 0.75, 0.1], [REF.steerFrontRight]: [0.15, -0.75, 0.1],
        [REF.steerRearLeft]: [-0.15, 0.75, 0.1], [REF.steerRearRight]: [-0.15, -0.75, 0.1],
        [REF.wheelFrontLeft]: [0.15, 1, 0], [REF.wheelFrontRight]: [0.15, -1, 0],
        [REF.wheelMiddleLeft]: [0, 1, 0], [REF.wheelMiddleRight]: [0, -1, 0],
        [REF.wheelRearLeft]: [-0.15, 1, 0], [REF.wheelRearRight]: [-0.15, -1, 0],
        [REF.mastBase]: [0, 0, 0.7], [REF.mastHead]: [0, 0, 1.25],
        [REF.armAzimuth]: [0.5, 0, 0.35], [REF.armShoulder]: [0.8, 0, 0.5],
        [REF.armElbow]: [1.05, 0, 0.6], [REF.armWrist]: [1.25, 0, 0.68],
        [REF.armTurret]: [1.45, 0, 0.78],
        [REF.hgaMast]: [-0.3, 0.5, 0.5], [REF.hgaDish]: [-0.45, 0.75, 0.85],
        [REF.antennaUhf]: [-0.35, -0.6, 0.6], [REF.antennaWhips]: [-0.5, -0.8, 0.45],
        [REF.solarLeft]: [0, 0.85, 0.3], [REF.solarRight]: [0, -0.85, 0.3],
        [REF.rtg]: [-0.95, 0, 0.15]
      };
      for (const [ref, vector] of Object.entries(vectors)) {
        m.get(ref).translate(vector.map((c) => c * d));
      }
    }
  }
};
