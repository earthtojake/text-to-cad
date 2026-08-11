const Z_AXIS = [0, 0, 1];
const ORIGIN = [0, 0, 0];

// Gear-stage constants mirrored from qdd_actuator.py (module 1.0, fixed ring).
const SUN_TEETH = 24;
const PLANET_TEETH = 30;
const RING_TEETH = 84;
// Fixed-ring planetary reduction: carrier = sun / (1 + Nr/Ns) = sun / 4.5.
const REDUCTION_RATIO = 1 + (RING_TEETH / SUN_TEETH);
const PLANET_CENTER_R = 27;
const PLANET_ANGLES_DEG = [90, 210, 330];

// 4.5 sun revolutions per cycle returns the carrier to exactly 360 deg. The
// rotor/sun end the cycle 180 deg from start, which is invisible: every
// rotating part is 180-deg symmetric (28 alternating magnets = 14 pole pairs,
// 24/30-tooth gears, 6x lightening + 4x coupling holes), so the loop is
// seamless at tooth/pole phase.
const DRIVE_CYCLE_DEG = REDUCTION_RATIO * 360;

// Rotor-bearing ball cage runs near half the inner-race speed; 4/9 (~0.444 vs
// the physical ~0.452 for this geometry) makes the 10-ball ring land exactly
// on its 36-deg symmetry at the end of the drive cycle.
const BALL_CAGE_RATIO = 4 / 9;
// Cross-roller cage: outer race fixed, inner race at carrier speed -> cage at
// half carrier speed. 16 alternating-tilt rollers repeat every 45 deg, and
// (360 / 2) = 180 deg per cycle closes on that symmetry.
const ROLLER_CAGE_RATIO = 0.5;

// Documented static exploded layout from qdd_actuator.py EXPLODE_OFFSETS
// (mm along Z at explode = 1), verified pairwise non-overlapping there.
const EXPLODE_OFFSETS_MM = {
  connectorPower: -82,
  connectorSignal: -82,
  rearCover: -64,
  driverPcb: -46,
  encoderPcb: -32,
  housing: 0,
  encoderMagnetRing: 70,
  rearBearing: 78,
  stator: 94,
  rotor: 128,
  frontBearing: 154,
  ringGear: 168,
  sunGear: 196,
  planetGear: 222,
  carrier: 250,
  crossRollerBearing: 280,
  frontRetainer: 298,
  retainerScrews: 312,
  torqueSensor: 330,
  outputFlange: 348,
  cableTube: 360
};
const PLANET_EXPLODE_RADIAL_MM = 14;

// The viewer floor sits at the assembled model's lowest geometry (the rear
// connectors). Rebase the explosion so the lowest station is 0: every part
// explodes upward or stays put, relative spacing is unchanged, and nothing
// sinks through the floor. The rear connectors keep their assembled height.
const FLOOR_LIFT_MM = -Math.min(...Object.values(EXPLODE_OFFSETS_MM));

// "Keep gear mesh" station: ring, sun, and planets explode together as one
// meshed cluster so the tooth engagement stays watchable; the carrier still
// lifts to its own documented station so its plate does not cover the mesh.
// The cluster spans z 6.8..20.5 mm; 210 keeps >60 mm clearance to the front
// bearing station (154) below and ~28 mm to the carrier station (250) above.
const GEAR_STAGE_CLUSTER_MM = 210;

const PLANETS = [
  { id: "planet1", angleDeg: PLANET_ANGLES_DEG[0] },
  { id: "planet2", angleDeg: PLANET_ANGLES_DEG[1] },
  { id: "planet3", angleDeg: PLANET_ANGLES_DEG[2] }
];

const SHELL_PARTS = [
  "housing",
  "frontRetainer",
  "retainerScrews",
  "rearCover",
  "connectorPower",
  "connectorSignal"
];
const ELECTRONICS_PARTS = ["driverPcb", "encoderPcb"];
const OUTPUT_STACK_PARTS = [
  "xrollerInner",
  "xrollerOuter",
  "xrollerRollers",
  "torqueSensor",
  "outputFlange"
];
const DRIVE_TRAIN_PARTS = ["sunGear", "planet1", "planet2", "planet3", "carrier"];

function finite(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(finite(value, min), min), max);
}

function clamp01(value) {
  return clamp(value, 0, 1);
}

function wrap01(cycle) {
  return ((finite(cycle, 0) % 1) + 1) % 1;
}

function planetCenter(angleDeg) {
  const angleRad = angleDeg * Math.PI / 180;
  return [
    PLANET_CENTER_R * Math.cos(angleRad),
    PLANET_CENTER_R * Math.sin(angleRad),
    14.5
  ];
}

function radialUnit(angleDeg) {
  const angleRad = angleDeg * Math.PI / 180;
  return [Math.cos(angleRad), Math.sin(angleRad), 0];
}

function applyVisibility(effects, params) {
  effects.visible("*", true);
  effects.visible(SHELL_PARTS, params.showShell !== false);
  effects.visible(ELECTRONICS_PARTS, params.showElectronics !== false);
  effects.visible(OUTPUT_STACK_PARTS, params.showOutputStack !== false);
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/renders/qdd_actuator/qdd_actuator.step"
    },
    label: "QDD actuator",
    description: "Quasi-direct-drive actuator with viewer-time drivetrain animation: the outrunner rotor spins the sun gear, three planets walk the fixed ring at the derived 4.5:1 reduction, and the carrier drives the torque sensor and output flange.",
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      housing: { ref: "#o1.1", label: "Housing", description: "Fixed finned aluminum housing." },
      frontRetainer: { ref: "#o1.2", label: "Front retainer ring" },
      rearCover: { ref: "#o1.3", label: "Rear cover" },
      retainerScrews: { ref: "#o1.4", label: "Retainer screws" },
      connectorPower: { ref: "#o1.5", label: "Power connector" },
      connectorSignal: { ref: "#o1.6", label: "Signal connector" },
      driverPcb: { ref: "#o1.7", label: "Driver PCB" },
      encoderPcb: { ref: "#o1.8", label: "Encoder PCB" },
      encoderMagnetRing: { ref: "#o1.9", label: "Encoder magnet ring", description: "Spins with the rotor for the rear magnetic encoder." },
      stator: { ref: "#o1.10", label: "Stator", description: "Fixed 24-slot stator and windings." },
      rotor: { ref: "#o1.11", label: "Rotor", description: "Outrunner rotor bell and 28-magnet ring; the animation input." },
      rearBearingInner: { ref: "#o1.12.1", label: "Rear bearing inner race" },
      rearBearingOuter: { ref: "#o1.12.2", label: "Rear bearing outer race" },
      rearBearingBalls: { ref: "#o1.12.3", label: "Rear bearing balls" },
      frontBearingInner: { ref: "#o1.13.1", label: "Front bearing inner race" },
      frontBearingOuter: { ref: "#o1.13.2", label: "Front bearing outer race" },
      frontBearingBalls: { ref: "#o1.13.3", label: "Front bearing balls" },
      sunGear: { ref: "#o1.14", label: "Sun gear (24T)", description: "Bolted to the rotor flange; rotates at input speed.", axis: Z_AXIS, origin: ORIGIN },
      ringGear: { ref: "#o1.15", label: "Ring gear (84T)", description: "Fixed internal gear pressed into the housing bore." },
      planet1: { ref: "#o1.16", label: "Planet gear 1 (30T)", axis: Z_AXIS, origin: planetCenter(PLANET_ANGLES_DEG[0]) },
      planet2: { ref: "#o1.17", label: "Planet gear 2 (30T)", axis: Z_AXIS, origin: planetCenter(PLANET_ANGLES_DEG[1]) },
      planet3: { ref: "#o1.18", label: "Planet gear 3 (30T)", axis: Z_AXIS, origin: planetCenter(PLANET_ANGLES_DEG[2]) },
      carrier: { ref: "#o1.19", label: "Planet carrier", description: "Output member at 1/4.5 of input speed.", axis: Z_AXIS, origin: ORIGIN },
      xrollerInner: { ref: "#o1.20.1", label: "Cross-roller inner ring", description: "Rotates with the output stage." },
      xrollerOuter: { ref: "#o1.20.2", label: "Cross-roller outer ring", description: "Fixed in the housing seat." },
      xrollerRollers: { ref: "#o1.20.3", label: "Cross-roller rollers" },
      torqueSensor: { ref: "#o1.21", label: "Torque sensor flexure", description: "Strain-gauge flexure between carrier and flange." },
      outputFlange: { ref: "#o1.22", label: "Output flange" },
      cableTube: { ref: "#o1.23", label: "Cable tube", description: "Static hollow-shaft cable conduit." }
    },
    parameters: {
      drive: {
        type: "number",
        label: "Drive",
        description: "Rotor/sun input angle over one closed mesh cycle (4.5 input revolutions = 1 carrier revolution).",
        default: 0,
        min: 0,
        max: DRIVE_CYCLE_DEG,
        step: 1,
        unit: "deg"
      },
      explode: {
        type: "number",
        label: "Explode",
        description: "Axial technical explosion from the documented build123d layout, applied after the gear motion.",
        default: 0,
        min: 0,
        max: 1,
        step: 0.01
      },
      keepGearMesh: {
        type: "boolean",
        label: "Keep gear mesh",
        description: "Explode the ring, sun, and planets together as one meshed cluster instead of separate stations; the carrier still lifts clear of the mesh.",
        default: true
      },
      showShell: { type: "boolean", label: "Housing shell", default: true },
      showElectronics: { type: "boolean", label: "Electronics", default: true },
      showOutputStack: { type: "boolean", label: "Output stack", default: true },
      highlightDrive: { type: "boolean", label: "Highlight gear train", default: false }
    },
    animations: {
      driveLoop: {
        label: "Drive 4.5:1 reduction",
        description: "Continuous rotor input: sun at input speed, planets walking the fixed ring, carrier and output flange at 1/4.5 speed.",
        duration: 12,
        loop: true,
        update({ cycle, set }) {
          set("drive", wrap01(cycle) * DRIVE_CYCLE_DEG);
        }
      },
      inspectExplode: {
        label: "Exploded drive inspection",
        description: "Same gear cycle while the stack separates into exploded stations and returns; the planetary stage stays meshed while 'Keep gear mesh' is on.",
        duration: 12,
        loop: true,
        update({ cycle, set }) {
          const phase = wrap01(cycle);
          set("drive", phase * DRIVE_CYCLE_DEG);
          set("explode", Math.sin(phase * Math.PI));
        }
      }
    }
  },

  update({ params, effects }) {
    const drive = finite(params.drive);
    const explode = clamp01(params.explode);
    const carrierAngle = drive / REDUCTION_RATIO;
    // Mesh-consistent planet spin about its own moving axis, relative to the
    // carrier frame: external sun/planet mesh reverses the relative rotation.
    const planetSpinRelativeToCarrier = -(SUN_TEETH / PLANET_TEETH) * (drive - carrierAngle);
    const ballOrbitAngle = drive * BALL_CAGE_RATIO;
    const rollerOrbitAngle = carrierAngle * ROLLER_CAGE_RATIO;
    const lift = (key) => (EXPLODE_OFFSETS_MM[key] + FLOOR_LIFT_MM) * explode;
    const keepGearMesh = params.keepGearMesh !== false;
    const gearLift = (key) => (keepGearMesh ? (GEAR_STAGE_CLUSTER_MM + FLOOR_LIFT_MM) * explode : lift(key));
    const planetRadialMm = keepGearMesh ? 0 : PLANET_EXPLODE_RADIAL_MM;

    applyVisibility(effects, params);

    if (params.highlightDrive === true) {
      effects.highlight(DRIVE_TRAIN_PARTS, true);
    }

    // Input group: rotor bell + magnets, encoder target ring, sun gear.
    effects.transform("rotor", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: drive },
      translate: [0, 0, lift("rotor")]
    });
    effects.transform("encoderMagnetRing", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: drive },
      translate: [0, 0, lift("encoderMagnetRing")]
    });
    effects.transform("sunGear", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: drive },
      translate: [0, 0, gearLift("sunGear")]
    });

    // Rotor support bearings: inner races spin with the hub, ball rings orbit
    // at cage speed, outer races stay seated in the housing sleeve.
    for (const [inner, balls, outer, key] of [
      ["rearBearingInner", "rearBearingBalls", "rearBearingOuter", "rearBearing"],
      ["frontBearingInner", "frontBearingBalls", "frontBearingOuter", "frontBearing"]
    ]) {
      effects.transform(inner, {
        rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: drive },
        translate: [0, 0, lift(key)]
      });
      effects.transform(balls, {
        rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: ballOrbitAngle },
        translate: [0, 0, lift(key)]
      });
      effects.transform(outer, { translate: [0, 0, lift(key)] });
    }

    // Planets: spin about their own (initial) axis, separate radially in the
    // exploded view, then orbit the sun axis with the carrier. Steps compose
    // in order in the fixed model frame, so the radial offset and orbit keep
    // the planets pointing outward at the current carrier angle.
    for (const planet of PLANETS) {
      const radial = radialUnit(planet.angleDeg);
      effects.transform(planet.id, {
        transforms: [
          {
            rotate: {
              axis: Z_AXIS,
              origin: planetCenter(planet.angleDeg),
              angleDeg: planetSpinRelativeToCarrier
            }
          },
          {
            translate: [
              radial[0] * planetRadialMm * explode,
              radial[1] * planetRadialMm * explode,
              gearLift("planetGear")
            ]
          },
          { rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle } }
        ]
      });
    }

    // Output group at carrier speed: carrier, torque sensor, flange, and the
    // cross-roller inner ring; the roller ring orbits at cage speed.
    effects.transform("carrier", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle },
      translate: [0, 0, lift("carrier")]
    });
    effects.transform("torqueSensor", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle },
      translate: [0, 0, lift("torqueSensor")]
    });
    effects.transform("outputFlange", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle },
      translate: [0, 0, lift("outputFlange")]
    });
    effects.transform("xrollerInner", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle },
      translate: [0, 0, lift("crossRollerBearing")]
    });
    effects.transform("xrollerRollers", {
      rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: rollerOrbitAngle },
      translate: [0, 0, lift("crossRollerBearing")]
    });
    effects.transform("xrollerOuter", { translate: [0, 0, lift("crossRollerBearing")] });

    // Static parts only take their exploded-station offsets.
    effects.transform("housing", { translate: [0, 0, lift("housing")] });
    effects.transform("ringGear", { translate: [0, 0, gearLift("ringGear")] });
    effects.transform("stator", { translate: [0, 0, lift("stator")] });
    effects.transform("frontRetainer", { translate: [0, 0, lift("frontRetainer")] });
    effects.transform("retainerScrews", { translate: [0, 0, lift("retainerScrews")] });
    effects.transform("rearCover", { translate: [0, 0, lift("rearCover")] });
    effects.transform("connectorPower", { translate: [0, 0, lift("connectorPower")] });
    effects.transform("connectorSignal", { translate: [0, 0, lift("connectorSignal")] });
    effects.transform("driverPcb", { translate: [0, 0, lift("driverPcb")] });
    effects.transform("encoderPcb", { translate: [0, 0, lift("encoderPcb")] });
    effects.transform("cableTube", { translate: [0, 0, lift("cableTube")] });
  }
};
