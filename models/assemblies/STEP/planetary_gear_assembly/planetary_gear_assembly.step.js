// Choreography for the planetary gear stage (copied into the sidecar at
// build; the viewer's Animation tab is the only consumer). Raw transforms by
// design: animation knows nothing of the mate graph, so the exact fixed-ring
// ratios are restated here.
const FULL_MESH_CYCLE_DEG = 1260;
const CARRIER_RATIO = 24 / (24 + 60);
const PLANET_RATIO = -(24 / 18) * (1 - CARRIER_RATIO);
const Z = [0, 0, 1];
const PLANETS = [
  { gear: "planet_gear_1_18_teeth", pin: "planet_pin_1", center: [42, 0, 0], radial: [1, 0, 0] },
  { gear: "planet_gear_2_18_teeth", pin: "planet_pin_2", center: [-21, 36.373067, 0], radial: [-0.5, 0.8660254, 0] },
  { gear: "planet_gear_3_18_teeth", pin: "planet_pin_3", center: [-21, -36.373067, 0], radial: [-0.5, -0.8660254, 0] },
];

function driveTrain(m, driveDeg) {
  const carrierDeg = driveDeg * CARRIER_RATIO;
  m.get("sun_gear_24_teeth").rotate(Z, driveDeg, [0, 0, 0]);
  m.get("carrier_plate").rotate(Z, carrierDeg, [0, 0, 0]);
  for (const planet of PLANETS) {
    const gear = m.get(planet.gear);
    // Spin about the planet's own (rest) center first, then orbit with the
    // carrier: successive calls premultiply, so the spin rides the orbit.
    gear.rotate(Z, driveDeg * PLANET_RATIO, planet.center);
    gear.rotate(Z, carrierDeg, [0, 0, 0]);
    m.get(planet.pin).rotate(Z, carrierDeg, [0, 0, 0]);
  }
}

const ease = { sine: (t) => 0.5 - 0.5 * Math.cos(Math.PI * 2 * t) };

export const clips = {
  meshCycle: {
    label: "Mesh cycle",
    duration: 6,
    update(t, m) {
      driveTrain(m, (t / 6) * FULL_MESH_CYCLE_DEG);
    },
  },
  inspectExplode: {
    label: "Explode inspect",
    duration: 5,
    update(t, m) {
      const progress = t / 5;
      driveTrain(m, progress * FULL_MESH_CYCLE_DEG);
      const explode = ease.sine(progress) * 16;
      for (const planet of PLANETS) {
        const shift = planet.radial.map((v) => v * explode);
        m.get(planet.gear).translate(shift);
        m.get(planet.pin).translate(shift);
      }
      m.get("sun_gear_24_teeth").translate([0, 0, (explode / 16) * 7]);
      m.get("carrier_plate").translate([0, 0, (explode / 16) * -4]);
      for (const planet of PLANETS) {
        m.get(planet.pin).translate([0, 0, (explode / 16) * -4]);
      }
    },
  },
};
