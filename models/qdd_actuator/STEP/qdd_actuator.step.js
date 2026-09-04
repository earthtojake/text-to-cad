// qdd_actuator.step.js — choreography for the QDD actuator.
//
// Two clips: the drive train running at its 4.5:1 reduction, and the same
// cycle while the stack separates into its documented exploded stations.
// Choreography is deliberately independent of the model's mates: the ratios
// below re-describe the same gear train in a few lines of arithmetic.

const Z = [0, 0, 1];
const ORIGIN = [0, 0, 0];

const SUN_TEETH = 24;
const PLANET_TEETH = 30;
const RING_TEETH = 84;
const REDUCTION_RATIO = 1 + RING_TEETH / SUN_TEETH; // 4.5:1, fixed ring
const PLANET_CENTER_R = 27;
const PLANET_Z = 14.5;
const PLANET_ANGLES_DEG = [90, 210, 330];

// 4.5 sun revolutions per cycle returns the carrier to exactly 360 deg. The
// rotor/sun end 180 deg from start, which is invisible: every rotating part is
// 180-deg symmetric, so the loop is seamless at tooth/pole phase.
const DRIVE_CYCLE_DEG = REDUCTION_RATIO * 360;
const BALL_CAGE_RATIO = 4 / 9;
const ROLLER_CAGE_RATIO = 0.5;

// Documented axial explosion stations (mm along Z at explode = 1), from the
// model's own EXPLODE_OFFSETS, verified pairwise non-overlapping there.
const STATION = {
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
  cableTube: 360,
};

// Rebase so the lowest station is 0: every part explodes upward or stays put,
// relative spacing unchanged, and nothing sinks through the viewer floor.
const FLOOR_LIFT = -Math.min(...Object.values(STATION));

// "Keep gear mesh" station: ring, sun, and planets lift together as one meshed
// cluster so the tooth engagement stays watchable; the carrier still lifts to
// its own station so its plate does not cover the mesh.
const GEAR_CLUSTER = 210;
const PLANET_RADIAL = 14;

// Occurrence targets. Parts are named by label; groups (subassemblies) must be
// named by occurrence id, which is what the label vocabulary cannot reach.
const T = {
  housing: "housing",
  frontRetainer: "front_retainer",
  retainerScrews: "#o1.4",
  rearCover: "rear_cover",
  connectorPower: "#o1.5",
  connectorSignal: "#o1.6",
  driverPcb: "#o1.7",
  encoderPcb: "#o1.8",
  encoderMagnetRing: "encoder_magnet_ring",
  stator: "#o1.10",
  rotor: "#o1.11",
  rearInner: "inner_race:rear",
  rearOuter: "outer_race:rear",
  rearBalls: "#o1.12.3",
  frontInner: "inner_race:front",
  frontOuter: "outer_race:front",
  frontBalls: "#o1.13.3",
  sunGear: "sun_gear",
  ringGear: "ring_gear",
  carrier: "planet_carrier",
  xrollerInner: "inner_ring",
  xrollerOuter: "outer_ring",
  xrollerRollers: "#o1.20.3",
  torqueSensor: "#o1.21",
  outputFlange: "output_flange",
  cableTube: "cable_tube",
};

function planetCenter(angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return [PLANET_CENTER_R * Math.cos(a), PLANET_CENTER_R * Math.sin(a), PLANET_Z];
}

function radialUnit(angleDeg) {
  const a = (angleDeg * Math.PI) / 180;
  return [Math.cos(a), Math.sin(a), 0];
}

/**
 * One frame of the drive train.
 *
 * @param m       the occurrence handle factory
 * @param drive   rotor/sun input angle in degrees
 * @param explode 0..1 axial explosion
 * @param keepMesh explode the planetary stage as one meshed cluster
 */
function frame(m, drive, explode, keepMesh) {
  const carrier = drive / REDUCTION_RATIO;
  // Mesh-consistent planet spin about its own moving axis, relative to the
  // carrier frame: the external sun/planet mesh reverses the relative rotation.
  const planetSpin = -(SUN_TEETH / PLANET_TEETH) * (drive - carrier);
  const ballOrbit = drive * BALL_CAGE_RATIO;
  const rollerOrbit = carrier * ROLLER_CAGE_RATIO;

  const lift = (key) => (STATION[key] + FLOOR_LIFT) * explode;
  const gearLift = (key) => (keepMesh ? (GEAR_CLUSTER + FLOOR_LIFT) * explode : lift(key));
  const planetRadial = keepMesh ? 0 : PLANET_RADIAL;

  // Input group: rotor bell + magnets, encoder target ring, sun gear.
  m.get(T.rotor).rotate(Z, drive, ORIGIN).translate([0, 0, lift("rotor")]);
  m.get(T.encoderMagnetRing)
    .rotate(Z, drive, ORIGIN)
    .translate([0, 0, lift("encoderMagnetRing")]);
  m.get(T.sunGear).rotate(Z, drive, ORIGIN).translate([0, 0, gearLift("sunGear")]);

  // Rotor support bearings: inner races spin with the hub, ball rings orbit at
  // cage speed, outer races stay seated in the housing sleeve.
  for (const [inner, balls, outer, key] of [
    [T.rearInner, T.rearBalls, T.rearOuter, "rearBearing"],
    [T.frontInner, T.frontBalls, T.frontOuter, "frontBearing"],
  ]) {
    m.get(inner).rotate(Z, drive, ORIGIN).translate([0, 0, lift(key)]);
    m.get(balls).rotate(Z, ballOrbit, ORIGIN).translate([0, 0, lift(key)]);
    m.get(outer).translate([0, 0, lift(key)]);
  }

  // Planets: spin about their own axis, separate radially when exploded, then
  // orbit the sun axis with the carrier. Successive calls PREMULTIPLY, so the
  // spin and the radial offset both ride the orbit.
  for (let i = 0; i < PLANET_ANGLES_DEG.length; i += 1) {
    const psi = PLANET_ANGLES_DEG[i];
    const radial = radialUnit(psi);
    m.get(`planet_gear:p${i + 1}`)
      .rotate(Z, planetSpin, planetCenter(psi))
      .translate([
        radial[0] * planetRadial * explode,
        radial[1] * planetRadial * explode,
        gearLift("planetGear"),
      ])
      .rotate(Z, carrier, ORIGIN);
  }

  // Output group at carrier speed; the roller ring orbits at cage speed.
  m.get(T.carrier).rotate(Z, carrier, ORIGIN).translate([0, 0, lift("carrier")]);
  m.get(T.torqueSensor).rotate(Z, carrier, ORIGIN).translate([0, 0, lift("torqueSensor")]);
  m.get(T.outputFlange).rotate(Z, carrier, ORIGIN).translate([0, 0, lift("outputFlange")]);
  m.get(T.xrollerInner)
    .rotate(Z, carrier, ORIGIN)
    .translate([0, 0, lift("crossRollerBearing")]);
  m.get(T.xrollerRollers)
    .rotate(Z, rollerOrbit, ORIGIN)
    .translate([0, 0, lift("crossRollerBearing")]);
  m.get(T.xrollerOuter).translate([0, 0, lift("crossRollerBearing")]);

  // Static members take their exploded station only.
  m.get(T.housing).translate([0, 0, lift("housing")]);
  m.get(T.ringGear).translate([0, 0, gearLift("ringGear")]);
  m.get(T.stator).translate([0, 0, lift("stator")]);
  m.get(T.frontRetainer).translate([0, 0, lift("frontRetainer")]);
  m.get(T.retainerScrews).translate([0, 0, lift("retainerScrews")]);
  m.get(T.rearCover).translate([0, 0, lift("rearCover")]);
  m.get(T.connectorPower).translate([0, 0, lift("connectorPower")]);
  m.get(T.connectorSignal).translate([0, 0, lift("connectorSignal")]);
  m.get(T.driverPcb).translate([0, 0, lift("driverPcb")]);
  m.get(T.encoderPcb).translate([0, 0, lift("encoderPcb")]);
  m.get(T.cableTube).translate([0, 0, lift("cableTube")]);
}

export const clips = {
  drive: {
    label: "Drive 4.5:1 reduction",
    duration: 12,
    loop: true,
    update(t, m) {
      frame(m, ((t / 12) % 1) * DRIVE_CYCLE_DEG, 0, true);
    },
  },
  inspect: {
    label: "Exploded drive inspection",
    duration: 12,
    loop: true,
    update(t, m) {
      const phase = (t / 12) % 1;
      frame(m, phase * DRIVE_CYCLE_DEG, Math.sin(phase * Math.PI), true);
    },
  },
  teardown: {
    label: "Full teardown",
    duration: 10,
    loop: true,
    update(t, m) {
      const phase = (t / 10) % 1;
      frame(m, 0, Math.sin(phase * Math.PI), false);
    },
  },
};
