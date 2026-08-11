// Live viewer parameters + animations for the lunar mass driver concept.
//
// The STEP geometry is baked in the "ready to launch" state: payload canister
// clamped on the levitated sled at its home berth on the breech apron,
// gantries docked over the track, dust shields closed, radiators at 60 deg,
// crawler rover parked under the transfer crane. Every animation is an exact
// loop that starts and ends in that baked state.
//
// All constants below mirror the defaults in lunar_mass_driver.step.py
// (MassDriverParams + layout constants). If the Python geometry parameters
// are changed and the model regenerated, refresh these mirrors: the track
// profile (trackFrame), counts (segments, gantries, wings, panels, rovers),
// and baked poses are position contracts, not live lookups.
//
// Model frame: mm, +X down-track toward the muzzle, +Z up, terrain top z=0.

const DEG = Math.PI / 180;
const X_AXIS = [1, 0, 0];
const Y_AXIS = [0, 1, 0];
const Z_AXIS = [0, 0, 1];

// --- Mirrored geometry defaults (lunar_mass_driver.step.py MassDriverParams) ------
const TRACK_LENGTH = 180000;
const NSEG = 12;
const SEG_LEN = TRACK_LENGTH / NSEG;
const CURVE_R = 220000;
const ELEV_DEG = 10;
const DECK = 2400;
const BED_T = 800;
const COIL_CENTER_Z = 1600;      // above deck top (segment-local)
const SHIELD_Y = 2780;
const HOME_S = -9000;            // baked sled center (breech apron)
const STOP_S = 174000;           // sled brake point at the muzzle
const PAYLOAD_BASE = [-9000, 0, 4690];   // baked canister center (world)
const SLED_PIVOT = [-9000, 0, 2400];     // deck point under the sled at home
const GANTRY_XS = [20000, 36000, 52000];
const GANTRY_PIVOT_Y = 6500;
const GANTRY_RETRACT_DEG = 120;
const CRANE_X = -9000;
const TROLLEY_BASE_Z = 9450;
const SPREADER_BASE_Z = 7700;
const RADIATOR_XS = Array.from({ length: 8 }, (_, i) => 42000 + i * 7000);
const RADIATOR_ROW_Y = -23000;
const RADIATOR_HINGE_Z = 1500;
const RADIATOR_BAKED_DEG = 60;
const SOLAR_WING_COUNT = 17;     // round(1800 m^2 / (16 m * 6.5 m))
const SOLAR_ROWS = [25000, 34000, 43000];
const SOLAR_X0 = 60000;
const SOLAR_PITCH = 17500;
const SOLAR_PANEL_Z = 3400;
const SOLAR_BAKED_DEG = 25;
const DUST_SHIELD_H = 2600;
const TOWER_BEACON = [2000, 14000, 24450]; // tower h 18000 + antenna 3150 + 3300
const ROVER_COUNT = 4;
// Rover 1 is the payload transporter, parked under the crane spur (yaw 90).
const ROVER_HOMES = [
  { x: CRANE_X, y: -11500, yaw: 90 },
  { x: 26000, y: -10000, yaw: 0 },
  { x: 68000, y: -10000, yaw: 0 },
  { x: 110000, y: -10000, yaw: 0 }
];
const ROVER_Z = 1100;            // chassis mid height (rotation origin)
const CRAWLER_DECK_AXIS_Z = 2490;  // canister axis when riding the crawler
const CRAWLER_LOCAL_OFFSET = -300; // cargo deck center along crawler +X
const LANDER_CRADLE = [25000, -25900, 4750]; // canister axis on the lander cradle
const CRAWLER_LOAD = { x: 25000, y: -23600 }; // crawler pose at lander hand-off (yaw 0)
const DRONE_HOMES = [
  { x: 40000, y: 3200, z: 9000 },
  { x: 120000, y: -3200, z: 12500 }
];
const MUZZLE_PLUME_BASE = [176000, -4800, 0];
const EXPLODE_SCALE = 14000;     // mm at exploded_distance = 1

const PALETTES = {
  spacex: { coil: "#2f8cff", conduit: "#00c8e6", glow: "#4fa3ff", recolor: false },
  aurora: { coil: "#19e6b8", conduit: "#8c59ff", glow: "#3af0cf", recolor: true },
  ember: { coil: "#ff7319", conduit: "#ffb82e", glow: "#ff8c3a", recolor: true }
};

// --- Track profile (mirror of lunar_mass_driver.step.py track_frame) --------------
const ELEV_RAD = ELEV_DEG * DEG;
const CURVE_ARC = CURVE_R * ELEV_RAD;
const CURVE_S0 = TRACK_LENGTH - CURVE_ARC;

function trackFrame(s) {
  if (s <= CURVE_S0) {
    return { x: s, z: DECK, pitch: 0 };
  }
  const phi = Math.min(ELEV_RAD, (s - CURVE_S0) / CURVE_R);
  let x = CURVE_S0 + CURVE_R * Math.sin(phi);
  let z = DECK + CURVE_R * (1 - Math.cos(phi));
  if (s > TRACK_LENGTH) {
    const extra = s - TRACK_LENGTH;
    x += extra * Math.cos(ELEV_RAD);
    z += extra * Math.sin(ELEV_RAD);
  }
  return { x, z, pitch: phi };
}

// Chord midpoint frame per segment (matches the Python placement).
const SEG_FRAMES = Array.from({ length: NSEG }, (_, i) => {
  const a = trackFrame(i * SEG_LEN);
  const b = trackFrame((i + 1) * SEG_LEN);
  return {
    x: (a.x + b.x) / 2,
    z: (a.z + b.z) / 2,
    pitch: Math.atan2(b.z - a.z, b.x - a.x)
  };
});

// --- Small math helpers ----------------------------------------------------
function clamp01(v) { return Math.min(1, Math.max(0, v)); }
function finite(v, fb = 0) { const n = Number(v); return Number.isFinite(n) ? n : fb; }
function win(t, a, b) { return clamp01((t - a) / (b - a)); }
function smooth(u) { const s = clamp01(u); return s * s * (3 - 2 * s); }
function lerp(a, b, u) { return a + (b - a) * u; }
function rotXY(x, y, deg) {
  const c = Math.cos(deg * DEG);
  const s = Math.sin(deg * DEG);
  return [x * c - y * s, x * s + y * c];
}

// Transform steps that carry a baked-at-home body to arc position s on the
// track (rotate about the home deck point, then translate along the profile).
function sledSteps(s) {
  const f = trackFrame(s);
  return [
    { rotate: { axis: Y_AXIS, origin: SLED_PIVOT, angleDeg: -(f.pitch / DEG) } },
    { translate: [f.x - HOME_S, 0, f.z - DECK] }
  ];
}

// Pose helper: place a body baked at basePos/baseYaw at (x, y, z, yawDeg).
function poseSteps(basePos, baseYaw, x, y, z, yawDeg) {
  return [
    { rotate: { axis: Z_AXIS, origin: basePos, angleDeg: yawDeg - baseYaw } },
    { translate: [x - basePos[0], y - basePos[1], z - basePos[2]] }
  ];
}

// Piecewise waypoint interpolation: [{u, x, y, yaw}] sorted by u.
function samplePath(path, u) {
  const t = clamp01(u);
  let a = path[0];
  let b = path[path.length - 1];
  for (let i = 0; i + 1 < path.length; i += 1) {
    if (t >= path[i].u && t <= path[i + 1].u) { a = path[i]; b = path[i + 1]; break; }
  }
  const span = Math.max(1e-9, b.u - a.u);
  const k = smooth((t - a.u) / span);
  return { x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k), yaw: lerp(a.yaw, b.yaw, k) };
}

// Crawler routes between the crane spur park and the lander hand-off point.
const CRAWL_OUT = [
  { u: 0.00, x: CRANE_X, y: -11500, yaw: 90 },
  { u: 0.08, x: CRANE_X, y: -10000, yaw: 90 },
  { u: 0.16, x: CRANE_X + 3000, y: -10000, yaw: 0 },
  { u: 0.70, x: 25000, y: -10000, yaw: 0 },
  { u: 0.82, x: 25000, y: -12500, yaw: -90 },
  { u: 0.94, x: CRAWLER_LOAD.x, y: CRAWLER_LOAD.y, yaw: -90 },
  { u: 1.00, x: CRAWLER_LOAD.x, y: CRAWLER_LOAD.y, yaw: 0 }
];
const CRAWL_BACK = [
  { u: 0.00, x: CRAWLER_LOAD.x, y: CRAWLER_LOAD.y, yaw: 0 },
  { u: 0.06, x: CRAWLER_LOAD.x, y: -12500, yaw: 45 },
  { u: 0.14, x: 25000 - 3000, y: -10000, yaw: 135 },
  { u: 0.16, x: 25000 - 4000, y: -10000, yaw: 180 },
  { u: 0.80, x: CRANE_X + 2000, y: -10000, yaw: 180 },
  { u: 0.90, x: CRANE_X, y: -10400, yaw: 245 },
  { u: 1.00, x: CRANE_X, y: -11500, yaw: 270 }
];

// --- Feature table (occurrence refs follow the root child order documented
// in lunar_mass_driver.step.py build_scene) ------------------------------------------
const features = {
  terrain: { ref: "#o1.1", label: "Lunar terrain" },
  earth: { ref: "#o1.2", label: "Earth in sky" },
  track: { ref: "#o1.3", label: "Launch track" },
  breech_terminal: { ref: "#o1.3.13", label: "Breech loading terminal" },
  muzzle_terminal: { ref: "#o1.3.14", label: "Muzzle terminal" },
  foundations: { ref: "#o1.4", label: "Regolith foundations" },
  sled: { ref: "#o1.5", label: "Levitated payload sled" },
  sled_carriage: { ref: "#o1.5.1", label: "Acceleration carriage" },
  sled_cradle: { ref: "#o1.5.2", label: "Payload cradle" },
  payload: { ref: "#o1.5.3", label: "Payload canister", origin: PAYLOAD_BASE },
  gantry_row: { ref: "#o1.6", label: "Service gantries" },
  loading_station: { ref: "#o1.7", label: "Payload loading station" },
  crane_trolley: { ref: "#o1.7.2.7", label: "Crane trolley" },
  crane_spreader: { ref: "#o1.7.2.8", label: "Crane spreader bar" },
  lander: { ref: "#o1.8", label: "Starship cargo lander" },
  tower: { ref: "#o1.9", label: "Launch control tower" },
  tower_beacon: { ref: "#o1.9.7", label: "Tower beacon", origin: TOWER_BEACON },
  solar_farm: { ref: "#o1.10", label: "Solar farm" },
  radiator_array: { ref: "#o1.11", label: "Radiator array" },
  power_system: { ref: "#o1.12", label: "Power distribution" },
  trunk_run: { ref: "#o1.12.5", label: "Power trunk run" },
  riser_run: { ref: "#o1.12.6", label: "Track power risers" },
  rover_fleet: { ref: "#o1.13", label: "Rover fleet" },
  drone_flight: { ref: "#o1.14", label: "Inspection drones" },
  dust: { ref: "#o1.15", label: "Regolith dust plumes" },
  pad_plume: { ref: "#o1.15.1", label: "Landing pad dust" },
  muzzle_plume: { ref: "#o1.15.2", label: "Muzzle dust", origin: MUZZLE_PLUME_BASE }
};
for (let j = 1; j <= NSEG; j += 1) {
  const base = `#o1.3.${j}`;
  features[`segment_${j}`] = { ref: base, label: `Track segment ${j}` };
  features[`segment_${j}_bed`] = { ref: `${base}.1`, label: `Segment ${j} bed truss` };
  features[`segment_${j}_rail_left`] = { ref: `${base}.2`, label: `Segment ${j} rail L` };
  features[`segment_${j}_rail_right`] = { ref: `${base}.3`, label: `Segment ${j} rail R` };
  features[`segment_${j}_coils`] = { ref: `${base}.4`, label: `Segment ${j} coils` };
  features[`segment_${j}_yokes`] = { ref: `${base}.5`, label: `Segment ${j} magnet housings` };
  features[`segment_${j}_shield_left`] = { ref: `${base}.6`, label: `Segment ${j} dust shield L` };
  features[`segment_${j}_shield_right`] = { ref: `${base}.7`, label: `Segment ${j} dust shield R` };
  features[`segment_${j}_tray`] = { ref: `${base}.8`, label: `Segment ${j} cable tray` };
  features[`segment_${j}_cooling_left`] = { ref: `${base}.9`, label: `Segment ${j} cooling loop L` };
  features[`segment_${j}_cooling_right`] = { ref: `${base}.10`, label: `Segment ${j} cooling loop R` };
}
for (let g = 1; g <= GANTRY_XS.length; g += 1) {
  features[`gantry_${g}`] = {
    ref: `#o1.6.${g}`,
    label: `Service gantry ${g}`,
    origin: [GANTRY_XS[g - 1], GANTRY_PIVOT_Y, 0]
  };
}
for (let w = 1; w <= SOLAR_WING_COUNT; w += 1) {
  const perRow = Math.ceil(SOLAR_WING_COUNT / SOLAR_ROWS.length);
  const row = Math.floor((w - 1) / perRow);
  const col = (w - 1) % perRow;
  features[`solar_panel_${w}`] = {
    ref: `#o1.10.${w + 1}.2`,
    label: `Solar wing panel ${w}`,
    origin: [SOLAR_X0 + col * SOLAR_PITCH, SOLAR_ROWS[row % SOLAR_ROWS.length], SOLAR_PANEL_Z]
  };
}
for (let r = 1; r <= RADIATOR_XS.length; r += 1) {
  features[`radiator_panel_${r}`] = {
    ref: `#o1.11.${r + 1}`,
    label: `Radiator panel ${r}`,
    origin: [RADIATOR_XS[r - 1], RADIATOR_ROW_Y, RADIATOR_HINGE_Z]
  };
}
for (let r = 1; r <= ROVER_COUNT; r += 1) {
  const home = ROVER_HOMES[r - 1];
  features[`rover_${r}`] = {
    ref: `#o1.13.${r}`,
    label: r === 1 ? "Payload transporter crawler" : `Construction rover ${r}`,
    origin: [home.x, home.y, ROVER_Z]
  };
  features[`rover_plume_${r}`] = { ref: `#o1.15.${r + 2}`, label: `Rover ${r} dust plume` };
}
for (let d = 1; d <= DRONE_HOMES.length; d += 1) {
  features[`drone_${d}`] = { ref: `#o1.14.${d}`, label: `Inspection drone ${d}` };
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/assemblies/lunar_mass_driver.step"
    },
    units: { length: "mm", angle: "deg", time: "s" },
    features,
    parameters: {
      launch_phase: {
        type: "number", label: "Launch sequence", default: 0, min: 0, max: 1, step: 0.001,
        description: "Master scrub through launch, payload release, and the reload run. 0 = idle ready state; overrides the manual sled/gantry controls while active."
      },
      sled_travel: {
        type: "number", label: "Sled travel", default: 0, min: 0, max: 1, step: 0.001,
        description: "Manual sled position along the track (payload attached). Ignored while the launch sequence runs."
      },
      coil_glow_intensity: {
        type: "number", label: "Coil glow", default: 0.85, min: 0, max: 2, step: 0.01,
        description: "Peak emissive intensity of the accelerator coil wave."
      },
      acceleration_visual_intensity: {
        type: "number", label: "Acceleration glow", default: 0.8, min: 0, max: 1, step: 0.01,
        description: "Sled-body glow strength during hard acceleration."
      },
      payload_release_angle: {
        type: "number", label: "Release angle", default: 10, min: 0, max: 25, step: 0.5, unit: "deg",
        description: "Departure angle of the canister after separation; the track muzzle itself is pitched 10 deg."
      },
      gantry_position: {
        type: "number", label: "Gantry retract", default: 0, min: 0, max: 1, step: 0.01,
        description: "Manual slew of the service gantry booms away from the track (0 docked, 1 fully retracted)."
      },
      dust_shield_position: {
        type: "number", label: "Dust shields", default: 1, min: 0, max: 1, step: 0.01,
        description: "1 = shields raised (closed) as baked; 0 = hinged fully open for maintenance access."
      },
      solar_panel_deploy_angle: {
        type: "number", label: "Solar tilt", default: 25, min: 0, max: 80, step: 0.5, unit: "deg",
        description: "Sun-tracking tilt of the solar wings about their row axis (baked at 25 deg)."
      },
      radiator_panel_angle: {
        type: "number", label: "Radiator deploy", default: 60, min: 0, max: 90, step: 0.5, unit: "deg",
        description: "Radiator panel angle above horizontal about the manifold hinge (baked at 60 deg)."
      },
      rover_patrol: {
        type: "number", label: "Site patrol", default: 0, min: 0, max: 1, step: 0.001,
        description: "Drives rovers along the service road and drones along the track; 0 parks everything at the baked poses."
      },
      coil_wave_phase: {
        type: "number", label: "Coil wave phase", default: 0, min: 0, max: 1, step: 0.001,
        description: "Inspection control: traveling-wave position for the coil test wave (no mechanism motion)."
      },
      lunar_dust_level: {
        type: "number", label: "Dust level", default: 0.5, min: 0, max: 1, step: 0.01,
        description: "Opacity of the schematic regolith dust plumes."
      },
      cutaway_fraction: {
        type: "number", label: "Cutaway", default: 0, min: 0, max: 1, step: 0.01,
        description: "Fades dust shields and magnet housings on the leading fraction of segments to reveal coils, rails, and sled."
      },
      exploded_distance: {
        type: "number", label: "Explode", default: 0, min: 0, max: 1, step: 0.01,
        description: "Separates terrain, track layers, sled stack, and site systems for the exploded reveal (14 m at full scale)."
      },
      earth_visibility: { type: "boolean", label: "Earth", default: true },
      starship_lander_visibility: { type: "boolean", label: "Cargo lander", default: true },
      accent_color_palette: {
        type: "select", label: "Accent palette", default: "spacex",
        description: "Recolors coil glow and power conduits (safety markings keep their baked color).",
        options: [
          { value: "spacex", label: "SpaceX blue" },
          { value: "aurora", label: "Aurora teal" },
          { value: "ember", label: "Ember orange" }
        ]
      }
    },
    animations: {
      launch_sequence: {
        label: "Launch + reload cycle",
        duration: 36,
        loop: true,
        update({ progress, set }) {
          set("launch_phase", progress >= 1 ? 0 : progress);
        }
      },
      coil_wave: {
        label: "Coil test wave",
        duration: 8,
        loop: true,
        update({ progress, set }) {
          // Encoded wave: 2.x carries the traveling-wave phase (see update()).
          set("launch_phase", 0);
          set("sled_travel", 0);
          set("coil_wave_phase", progress);
        }
      },
      deploy_systems: {
        label: "Thermal + power deploy",
        duration: 12,
        loop: true,
        update({ progress, set }) {
          const swell = 0.5 - 0.5 * Math.cos(2 * Math.PI * progress);
          set("radiator_panel_angle", 15 + 65 * swell);
          set("solar_panel_deploy_angle", 10 + 55 * Math.pow(Math.sin(Math.PI * progress), 2));
          set("dust_shield_position", 1 - swell);
          set("gantry_position", swell);
        }
      },
      site_operations: {
        label: "Rovers + drones patrol",
        duration: 18,
        loop: true,
        update({ progress, set }) {
          set("rover_patrol", progress >= 1 ? 0 : progress);
        }
      },
      exploded_reveal: {
        label: "Exploded reveal",
        duration: 14,
        loop: true,
        update({ progress, set }) {
          const e = Math.sin(Math.PI * progress);
          set("exploded_distance", smoothExplode(e));
          set("cutaway_fraction", 0.55 * e);
        }
      }
    }
  },

  update({ params, effects }) {
    const pal = PALETTES[params.accent_color_palette] || PALETTES.spacex;
    const glow = finite(params.coil_glow_intensity, 0.85);
    const accel = clamp01(finite(params.acceleration_visual_intensity, 0.8));
    const dustLevel = clamp01(finite(params.lunar_dust_level, 0.5));
    const releaseDeg = finite(params.payload_release_angle, 10);
    const t = clamp01(finite(params.launch_phase, 0));
    const running = t > 0 && t < 1;
    const wavePhase = clamp01(finite(params.coil_wave_phase, 0));

    // ---- Choreography state -------------------------------------------
    // Sled arc position.
    let sledS = HOME_S;
    if (running) {
      if (t < 0.08) sledS = HOME_S;
      else if (t < 0.22) sledS = HOME_S + (STOP_S - HOME_S) * Math.pow(win(t, 0.08, 0.22), 2);
      else if (t < 0.30) sledS = STOP_S;
      else if (t < 0.44) sledS = STOP_S - (STOP_S - HOME_S) * smooth(win(t, 0.30, 0.44));
      else sledS = HOME_S;
    } else {
      sledS = HOME_S + (STOP_S - HOME_S) * clamp01(finite(params.sled_travel, 0));
    }
    const sledMove = sledSteps(sledS);
    effects.transform(["sled_carriage", "sled_cradle"], { transforms: sledMove });

    // Gantry slew (staggered during the sequence, manual otherwise).
    for (let g = 1; g <= GANTRY_XS.length; g += 1) {
      let slew = clamp01(finite(params.gantry_position, 0));
      if (running) {
        const lead = (g - 1) * 0.015;
        const out = smooth(win(t, 0.0 + lead, 0.075 + lead));
        const back = smooth(win(t, 0.34 + lead, 0.44 + lead));
        slew = out - back;
      }
      effects.transform(`gantry_${g}`, {
        rotate: {
          axis: Z_AXIS,
          origin: [GANTRY_XS[g - 1], GANTRY_PIVOT_Y, 0],
          angleDeg: GANTRY_RETRACT_DEG * clamp01(slew)
        }
      });
    }

    // Dust shields: hinged skirts swing open about their bottom edge.
    let shieldClosed = clamp01(finite(params.dust_shield_position, 1));
    if (running) {
      const open = smooth(win(t, 0.46, 0.52)) - smooth(win(t, 0.86, 0.92));
      shieldClosed = 1 - open;
    }
    const shieldOpenDeg = 75 * (1 - shieldClosed);
    if (shieldOpenDeg > 0.01) {
      for (let j = 1; j <= NSEG; j += 1) {
        const f = SEG_FRAMES[j - 1];
        const axis = [Math.cos(f.pitch), 0, Math.sin(f.pitch)];
        const hingeZ = f.z - BED_T;
        effects.transform(`segment_${j}_shield_left`, {
          rotate: { axis, origin: [f.x, SHIELD_Y, hingeZ], angleDeg: -shieldOpenDeg }
        });
        effects.transform(`segment_${j}_shield_right`, {
          rotate: { axis, origin: [f.x, -SHIELD_Y, hingeZ], angleDeg: shieldOpenDeg }
        });
      }
    }

    // Radiators + solar wings (deltas from the baked angles).
    const radiatorDeg = finite(params.radiator_panel_angle, RADIATOR_BAKED_DEG);
    let radiatorDelta = radiatorDeg - RADIATOR_BAKED_DEG;
    if (running) {
      // Thermal load bump while the coils charge and fire, settling by t=1.
      radiatorDelta += 18 * (smooth(win(t, 0.02, 0.1)) - smooth(win(t, 0.55, 0.85)));
    }
    for (let r = 1; r <= RADIATOR_XS.length; r += 1) {
      effects.transform(`radiator_panel_${r}`, {
        rotate: {
          axis: X_AXIS,
          origin: [RADIATOR_XS[r - 1], RADIATOR_ROW_Y, RADIATOR_HINGE_Z],
          angleDeg: -radiatorDelta
        }
      });
    }
    const solarDeg = finite(params.solar_panel_deploy_angle, SOLAR_BAKED_DEG);
    let solarDelta = solarDeg - SOLAR_BAKED_DEG;
    if (running) {
      solarDelta += 6 * Math.sin(2 * Math.PI * t); // slow sun-tracking drift
    }
    for (let w = 1; w <= SOLAR_WING_COUNT; w += 1) {
      const origin = features[`solar_panel_${w}`].origin;
      effects.transform(`solar_panel_${w}`, {
        rotate: { axis: X_AXIS, origin, angleDeg: -solarDelta }
      });
    }

    // ---- Payload canister ----------------------------------------------
    let payloadOpacity = 1;
    if (!running || t < 0.22 || t >= 0.74) {
      // Clamped on the sled (identity relative to the sled motion).
      effects.transform("payload", { transforms: sledMove });
    } else if (t < 0.30) {
      // Ballistic separation from the muzzle. The pose at tau=0 must equal
      // the carried (sledSteps) pose exactly: sledSteps rotates by -pitch
      // about +Y, which carries the canister to x = fS.x - rel*sin(pitch),
      // and the canister pitch blends from the track pitch to releaseDeg.
      const tau = win(t, 0.22, 0.30);
      const fS = trackFrame(STOP_S);
      const trackPitchDeg = fS.pitch / DEG;
      const rel = PAYLOAD_BASE[2] - DECK;
      const c0 = [fS.x - rel * Math.sin(fS.pitch), 0, fS.z + rel * Math.cos(fS.pitch)];
      const aimDeg = lerp(trackPitchDeg, releaseDeg, smooth(Math.min(1, tau * 4)));
      const dir = [Math.cos(aimDeg * DEG), 0, Math.sin(aimDeg * DEG)];
      const fly = 42000 * tau;
      const sag = 2600 * tau * tau;
      effects.transform("payload", {
        transforms: [
          { rotate: { axis: Y_AXIS, origin: PAYLOAD_BASE, angleDeg: -aimDeg } },
          {
            translate: [
              c0[0] + dir[0] * fly - PAYLOAD_BASE[0],
              0,
              c0[2] + dir[2] * fly - sag - PAYLOAD_BASE[2]
            ]
          }
        ]
      });
      payloadOpacity = 1 - smooth(win(tau, 0.6, 1));
    } else if (t < 0.44) {
      // Off-scene; parked (invisible) at the lander cradle awaiting fade-in.
      effects.transform("payload", {
        transforms: poseSteps(PAYLOAD_BASE, 0,
          LANDER_CRADLE[0], LANDER_CRADLE[1], LANDER_CRADLE[2], 0)
      });
      payloadOpacity = smooth(win(t, 0.40, 0.44));
    } else if (t < 0.62) {
      // Riding the crawler back to the crane spur.
      const u = win(t, 0.44, 0.62);
      const hand = smooth(win(u, 0, 0.05));
      const pose = samplePath(CRAWL_BACK, u);
      const off = rotXY(CRAWLER_LOCAL_OFFSET, 0, pose.yaw);
      const x = lerp(LANDER_CRADLE[0], pose.x + off[0], hand);
      const y = lerp(LANDER_CRADLE[1], pose.y + off[1], hand);
      const z = lerp(LANDER_CRADLE[2], CRAWLER_DECK_AXIS_Z, hand);
      effects.transform("payload", {
        transforms: poseSteps(PAYLOAD_BASE, 0, x, y, z, lerp(0, pose.yaw, hand))
      });
    } else {
      // Crane hoist: lift, traverse over the apron, lower onto the sled.
      const park = samplePath(CRAWL_BACK, 1);
      const off = rotXY(CRAWLER_LOCAL_OFFSET, 0, park.yaw);
      const px = park.x + off[0];
      const py = park.y + off[1];
      const up = smooth(win(t, 0.62, 0.66));
      const across = smooth(win(t, 0.66, 0.70));
      const down = smooth(win(t, 0.70, 0.74));
      const x = lerp(px, PAYLOAD_BASE[0], across);
      const y = lerp(py, PAYLOAD_BASE[1], across);
      const z = lerp(lerp(CRAWLER_DECK_AXIS_Z, 6200, up), PAYLOAD_BASE[2], down);
      const yaw = lerp(park.yaw, 360, across); // 270 -> 360 (= baked heading)
      effects.transform("payload", {
        transforms: poseSteps(PAYLOAD_BASE, 0, x, y, z, yaw)
      });
    }
    effects.style("payload", { opacity: payloadOpacity, edgeOpacity: payloadOpacity });

    // Crane trolley + spreader follow the hoist.
    if (running && t >= 0.56 && t < 0.82) {
      const park = samplePath(CRAWL_BACK, 1);
      const off = rotXY(CRAWLER_LOCAL_OFFSET, 0, park.yaw);
      const py = park.y + off[1];
      const pre = smooth(win(t, 0.56, 0.62));
      const across = smooth(win(t, 0.66, 0.70));
      const down = smooth(win(t, 0.70, 0.74));
      const back = smooth(win(t, 0.76, 0.82));
      const y = lerp(pre * py, 0, Math.max(across, back));
      const upZ = lerp(lerp(SPREADER_BASE_Z, CRAWLER_DECK_AXIS_Z + 1450, pre),
        6200 + 1450, smooth(win(t, 0.62, 0.66)));
      const z = lerp(lerp(upZ, PAYLOAD_BASE[2] + 1450, down), SPREADER_BASE_Z, back);
      effects.transform("crane_trolley", { translate: [0, y, 0] });
      effects.transform("crane_spreader", { translate: [0, y, z - SPREADER_BASE_Z] });
    }

    // Clamp engage pulse after the payload seats.
    if (running && t >= 0.74 && t < 0.8) {
      const pulse = Math.sin(Math.PI * win(t, 0.74, 0.8));
      effects.style("sled_cradle", { emissive: "#ff2d2d", emissiveIntensity: 0.5 * pulse });
    }

    // ---- Coil wave + acceleration glow ---------------------------------
    let waveCenter = null; // in segment units along the tunnel
    let waveGain = 0;
    let base = 0;
    if (running) {
      base = 0.35 * (smooth(win(t, 0.02, 0.08)) - smooth(win(t, 0.30, 0.42)));
      if (t >= 0.08 && t < 0.30) {
        waveCenter = Math.max(0, sledS) / SEG_LEN;
        // Ramp ignition in and decay after release so intensity never steps.
        waveGain = smooth(win(t, 0.08, 0.10)) * (t < 0.22 ? 1 : 1 - smooth(win(t, 0.22, 0.30)));
      }
    } else if (wavePhase > 0 && wavePhase < 1) {
      // Fade the whole wave near the loop seam so phase 0/1 matches the
      // idle (dark) state with no single-frame flicker.
      const seamEnvelope = smooth(Math.min(1, Math.min(wavePhase, 1 - wavePhase) * 12));
      waveCenter = lerp(-2.5, NSEG + 2.5, wavePhase);
      waveGain = seamEnvelope;
      base = 0.12 * seamEnvelope;
    } else if (!running && sledS > 0) {
      waveCenter = sledS / SEG_LEN;
      waveGain = 1;
    }
    for (let j = 1; j <= NSEG; j += 1) {
      let intensity = base * glow;
      if (waveCenter !== null) {
        const d = (j - 0.5) - waveCenter;
        intensity += glow * waveGain * Math.exp(-(d * d) / (2 * 1.35 * 1.35));
      }
      effects.style(`segment_${j}_coils`, {
        emissive: pal.glow,
        emissiveIntensity: Math.min(2.5, intensity)
      });
      if (pal.recolor) {
        effects.style(`segment_${j}_coils`, { color: pal.coil });
      }
    }
    const sledGlow = waveCenter !== null && waveGain > 0 && (running ? t >= 0.08 && t < 0.3 : sledS > 0)
      ? accel * (0.25 + 0.55 * waveGain)
      : 0;
    effects.style("sled_carriage", {
      emissive: pal.glow,
      emissiveIntensity: sledGlow
    });

    // Tower beacon breathes while the launcher is armed (fades in and out).
    const armedEnvelope = running
      ? smooth(win(t, 0.02, 0.05)) * (1 - smooth(win(t, 0.27, 0.30)))
      : 0;
    effects.style("tower_beacon", {
      emissive: "#ff2d2d",
      emissiveIntensity: armedEnvelope * (0.4 + 0.4 * Math.sin(20 * Math.PI * t))
    });

    // ---- Rovers, crawler, drones, dust ----------------------------------
    const q = clamp01(finite(params.rover_patrol, 0));
    const roverSpeeds = [0, 0, 0, 0];
    // Crawler (rover 1) runs its delivery route during the launch sequence.
    if (running && t >= 0.34 && t < 0.80) {
      let pose;
      if (t < 0.42) pose = samplePath(CRAWL_OUT, win(t, 0.34, 0.42));
      else if (t < 0.62) pose = samplePath(CRAWL_BACK, win(t, 0.44, 0.62));
      else {
        const spin = smooth(win(t, 0.74, 0.80));
        const park = samplePath(CRAWL_BACK, 1);
        pose = { x: park.x, y: park.y, yaw: lerp(park.yaw, 450, spin) }; // 270 -> 450 (= 90 baked)
      }
      const home = ROVER_HOMES[0];
      const steps = poseSteps([home.x, home.y, ROVER_Z], home.yaw, pose.x, pose.y, ROVER_Z, pose.yaw);
      effects.transform("rover_1", { transforms: steps });
      effects.transform("rover_plume_1", { transforms: steps });
      // Ramped, not binary, so the plume opacity never steps.
      roverSpeeds[0] =
        smooth(win(t, 0.34, 0.36)) * (1 - smooth(win(t, 0.40, 0.42)))
        + smooth(win(t, 0.44, 0.46)) * (1 - smooth(win(t, 0.60, 0.62)));
    }
    // Patrol rovers sweep the road; everything returns home at q = 0/1.
    if (q > 0 && q < 1) {
      const amps = [0, 14000, 22000, 18000];
      const swing = Math.sin(2 * Math.PI * q);
      // Plume-activity envelope: |cos| is 1 at the seam, so fade the plume
      // activity near q = 0/1 to match the idle state without a step.
      const patrolSeam = smooth(Math.min(1, Math.min(q, 1 - q) * 10));
      const vel = Math.cos(2 * Math.PI * q);
      for (let r = 2; r <= Math.min(ROVER_COUNT, ROVER_HOMES.length); r += 1) {
        const home = ROVER_HOMES[r - 1];
        const dx = amps[r - 1] * swing;
        // Face +X while driving east, swing smoothly to 180 while driving west.
        const yaw = home.yaw + (vel < 0 ? 180 * smooth(Math.min(1, -vel * 4)) : 0);
        const steps = poseSteps([home.x, home.y, ROVER_Z], home.yaw, home.x + dx, home.y, ROVER_Z, yaw);
        effects.transform(`rover_${r}`, { transforms: steps });
        effects.transform(`rover_plume_${r}`, { transforms: steps });
        roverSpeeds[r - 1] = Math.abs(vel) * patrolSeam;
      }
      for (let d = 1; d <= DRONE_HOMES.length; d += 1) {
        const home = DRONE_HOMES[d - 1];
        const phase = 2 * Math.PI * q;
        const dx = (d === 1 ? 48000 : -52000) * Math.sin(phase);
        const dz = 900 * Math.sin(2 * phase) + 400 * Math.sin(3 * phase);
        const dy = (d === 1 ? 2200 : -2600) * Math.sin(2 * phase);
        effects.transform(`drone_${d}`, { translate: [dx, dy, dz] });
      }
    } else if (running) {
      for (let d = 1; d <= DRONE_HOMES.length; d += 1) {
        const bob = 600 * Math.sin(4 * Math.PI * t) * (d === 1 ? 1 : -1);
        effects.transform(`drone_${d}`, { translate: [0, 0, bob] });
      }
    }

    // Dust plume styling: ambient level plus launch/driving activity.
    const plumeBase = 0.42 * dustLevel;
    effects.style("pad_plume", { opacity: plumeBase * 0.8, edgeOpacity: 0 });
    let muzzleBoost = 0;
    if (running) {
      muzzleBoost = smooth(win(t, 0.18, 0.26)) - smooth(win(t, 0.34, 0.5));
      if (muzzleBoost > 0.01) {
        effects.transform("muzzle_plume", {
          scale: 1 + 1.6 * muzzleBoost,
          origin: MUZZLE_PLUME_BASE
        });
      }
    }
    effects.style("muzzle_plume", {
      opacity: Math.min(1, plumeBase * (0.6 + 1.4 * muzzleBoost)),
      edgeOpacity: 0
    });
    for (let r = 1; r <= ROVER_COUNT; r += 1) {
      const moving = roverSpeeds[r - 1] || 0;
      effects.style(`rover_plume_${r}`, {
        opacity: plumeBase * (0.25 + 0.75 * moving),
        edgeOpacity: 0
      });
    }

    // ---- Cutaway --------------------------------------------------------
    const cut = clamp01(finite(params.cutaway_fraction, 0));
    if (cut > 0) {
      const cutSegs = cut * NSEG;
      for (let j = 1; j <= NSEG; j += 1) {
        const k = clamp01(cutSegs - (j - 1));
        if (k <= 0) continue;
        const opacity = lerp(1, 0.1, k);
        for (const part of ["shield_left", "shield_right", "yokes"]) {
          effects.style(`segment_${j}_${part}`, { opacity, edgeOpacity: lerp(1, 0.3, k) });
        }
      }
    }

    // ---- Exploded reveal -------------------------------------------------
    const explode = clamp01(finite(params.exploded_distance, 0)) * EXPLODE_SCALE;
    if (explode > 0) {
      const shift = (target, dx, dy, dz) => effects.transform(target, {
        translate: [dx * explode, dy * explode, dz * explode]
      });
      shift("terrain", 0, 0, -0.5);
      shift("earth", 0, 0, 0.4);
      shift("foundations", 0, 0, -0.2);
      shift("gantry_row", 0, 0.8, 0.3);
      shift("loading_station", -0.6, -0.5, 0.2);
      shift("lander", 0.3, -0.9, 0.2);
      shift("tower", -0.5, 0.7, 0.3);
      shift("solar_farm", 0.2, 0.9, 0.35);
      shift("radiator_array", 0.2, -0.9, 0.35);
      shift("power_system", 0, -0.6, -0.15);
      shift("rover_fleet", 0, -0.4, 0.15);
      shift("drone_flight", 0, 0, 0.8);
      shift("dust", 0, 0, 0.1);
      shift("breech_terminal", -0.3, 0, 0.35);
      shift("muzzle_terminal", 0.4, 0, 0.45);
      shift("sled_carriage", 0, 0, 0.8);
      shift("sled_cradle", 0, 0, 1.05);
      shift("payload", 0, 0, 1.4);
      for (let j = 1; j <= NSEG; j += 1) {
        shift(`segment_${j}_bed`, 0, 0, 0.35);
        shift(`segment_${j}_rail_left`, 0, 0, 0.52);
        shift(`segment_${j}_rail_right`, 0, 0, 0.52);
        shift(`segment_${j}_coils`, 0, 0, 0.95);
        shift(`segment_${j}_yokes`, 0, 0, 0.68);
        shift(`segment_${j}_shield_left`, 0, 0.45, 0.4);
        shift(`segment_${j}_shield_right`, 0, -0.45, 0.4);
        shift(`segment_${j}_tray`, 0, -0.3, 0.25);
        shift(`segment_${j}_cooling_left`, 0, 0.28, 0.3);
        shift(`segment_${j}_cooling_right`, 0, -0.28, 0.3);
      }
    }

    // ---- Palette recolor + visibility -----------------------------------
    if (pal.recolor) {
      effects.style("riser_run", { color: pal.conduit });
      for (let k = 1; k <= 3; k += 1) {
        effects.style({ ref: `#o1.12.5.${k}` }, { color: pal.conduit });
        effects.style({ ref: `#o1.12.${k}.4` }, { color: pal.conduit });
      }
      for (let j = 1; j <= NSEG; j += 1) {
        for (let k = 2; k <= 4; k += 1) {
          effects.style({ ref: `#o1.3.${j}.8.${k}` }, { color: pal.conduit });
        }
      }
    }
    effects.visible("earth", params.earth_visibility !== false);
    effects.visible("lander", params.starship_lander_visibility !== false);
  }
};

// Slightly overshoot-free easing for the exploded sweep.
function smoothExplode(e) {
  return clamp01(e * e * (3 - 2 * e));
}
