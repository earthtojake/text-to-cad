const Z_AXIS = [0, 0, 1];
const ORIGIN = [0, 0, 0];
const PLANETS = ["planet1", "planet2", "planet3"];
const PINS = ["pin1", "pin2", "pin3"];
const SUN_TEETH = 24;
const PLANET_TEETH = 18;
const RING_TEETH = 60;
// Fixed-ring planetary kinematics: carrier follows the sun by Ns / (Ns + Nr).
const CARRIER_RATIO_FIXED_RING = SUN_TEETH / (SUN_TEETH + RING_TEETH);
// 3.5 sun revolutions returns the carrier to 360 deg and each gear to an equivalent tooth phase.
const FULL_MESH_CYCLE_DEG = 1260;

let orbitGuide = null;

function finite(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function radialUnit(feature) {
  const center = Array.isArray(feature?.center) ? feature.center : ORIGIN;
  const length = Math.hypot(center[0] || 0, center[1] || 0);
  if (length <= 1e-6) {
    return [1, 0, 0];
  }
  return [(center[0] || 0) / length, (center[1] || 0) / length, 0];
}

function scaled(vector, scale) {
  return vector.map((value) => value * scale);
}

function createOrbitGuide(THREE) {
  const radius = 42;
  const points = [];
  for (let index = 0; index < 144; index += 1) {
    const angle = (index / 144) * Math.PI * 2;
    points.push(new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, 4));
  }
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({
    color: 0x94a3b8,
    transparent: true,
    opacity: 0.34,
    depthWrite: false
  });
  const line = new THREE.LineLoop(geometry, material);
  line.name = "planetary-gear-orbit-guide";
  line.renderOrder = 30;
  return line;
}

export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/step/assemblies/planetary_gear_assembly.step"
    },
    units: {
      length: "mm",
      angle: "deg",
      time: "s"
    },
    features: {
      carrier: { ref: "#o1.1.1", label: "Carrier plate", description: "The plate that carries planet pins around the sun axis." },
      ring: { ref: "#o1.2.1", label: "Ring gear", description: "Stationary internal gear, visually faded or hidden by controls." },
      sun: { ref: "#o1.3.1", label: "Sun gear", description: "Central driven gear." },
      planet1: { ref: "#o1.4.1", label: "Planet gear 1" },
      pin1: { ref: "#o1.5.1", label: "Planet pin 1" },
      planet2: { ref: "#o1.6.1", label: "Planet gear 2" },
      pin2: { ref: "#o1.7.1", label: "Planet pin 2" },
      planet3: { ref: "#o1.8.1", label: "Planet gear 3" },
      pin3: { ref: "#o1.9.1", label: "Planet pin 3" }
    },
    parameters: {
      drive: { type: "number", label: "Drive", description: "Sun gear input angle across one closed mesh cycle.", default: 0, min: 0, max: FULL_MESH_CYCLE_DEG, step: 1, unit: "deg" },
      explode: { type: "number", label: "Explode", description: "Radially separates meshing features for inspection.", default: 0, min: 0, max: 1, step: 0.01 },
      ringVisible: { type: "boolean", label: "Ring gear", default: true },
      orbitGuides: { type: "boolean", label: "Orbit guide", default: false },
      highlightMeshing: { type: "boolean", label: "Mesh highlight", default: false },
      viewMode: {
        type: "select",
        label: "View",
        default: "mesh",
        options: [
          { value: "mesh", label: "Mesh study" },
          { value: "cutaway", label: "Cutaway" },
          { value: "carrier", label: "Carrier focus" }
        ]
      }
    },
    animations: {
      meshCycle: {
        label: "Mesh cycle",
        duration: 6,
        loop: true,
        update({ cycle, set }) {
          set("drive", (cycle % 1) * FULL_MESH_CYCLE_DEG);
        }
      },
      inspectExplode: {
        label: "Explode inspect",
        duration: 5,
        loop: true,
        update({ progress, set }) {
          set("drive", progress * FULL_MESH_CYCLE_DEG);
          set("explode", Math.sin(progress * Math.PI));
        }
      }
    }
  },

  setup({ THREE, modelGroup, cleanup }) {
    if (!THREE || !modelGroup) {
      return;
    }
    orbitGuide = createOrbitGuide(THREE);
    modelGroup.add(orbitGuide);
    cleanup(() => {
      modelGroup.remove(orbitGuide);
      orbitGuide.geometry?.dispose?.();
      orbitGuide.material?.dispose?.();
      orbitGuide = null;
    });
  },

  update({ params, features, effects, time }) {
    const drive = finite(params.drive);
    const explode = finite(params.explode);
    const sunAngle = drive;
    const carrierAngle = sunAngle * CARRIER_RATIO_FIXED_RING;
    const planetSpinRelativeToCarrier = -(SUN_TEETH / PLANET_TEETH) * (sunAngle - carrierAngle);
    const lift = explode * 7;
    const cutaway = params.viewMode === "cutaway";
    const carrierFocus = params.viewMode === "carrier";
    const highlight = params.highlightMeshing === true &&
      (!time.playing || (time.progress > 0.45 && time.progress < 0.6));

    if (orbitGuide) {
      orbitGuide.visible = params.orbitGuides !== false;
      orbitGuide.rotation.z = (carrierAngle * Math.PI) / 180;
    }

    effects.visible("ring", params.ringVisible !== false);
    effects.style("ring", {
      opacity: cutaway ? 0.22 : 1,
      edgeOpacity: cutaway ? 0.38 : 1
    });
    effects.style("sun", {
      emissive: highlight ? "#7c2d12" : "",
      emissiveIntensity: highlight ? 0.32 : 0
    });
    effects.style(PLANETS, {
      emissive: highlight ? "#075985" : "",
      emissiveIntensity: highlight ? 0.22 : 0
    });
    effects.style(PINS, {
      opacity: 1
    });
    effects.style("carrier", {
      opacity: 1,
      emissive: carrierFocus ? "#14532d" : "",
      emissiveIntensity: carrierFocus ? 0.2 : 0
    });

    if (highlight) {
      effects.highlight(["sun", ...PLANETS], true);
    }

    effects.transform("sun", {
      transforms: [
        { rotate: { axis: Z_AXIS, origin: features.sun.center, angleDeg: sunAngle } },
        { translate: [0, 0, lift] }
      ]
    });
    effects.transform("carrier", {
      transforms: [
        { rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle } },
        { translate: [0, 0, -explode * 4] }
      ]
    });

    for (const planetId of PLANETS) {
      const radial = radialUnit(features[planetId]);
      effects.transform(planetId, {
        transforms: [
          { rotate: { axis: Z_AXIS, origin: features[planetId].center, angleDeg: planetSpinRelativeToCarrier } },
          { translate: scaled(radial, explode * 16) },
          { rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle } }
        ]
      });
    }

    for (const pinId of PINS) {
      const radial = radialUnit(features[pinId]);
      effects.transform(pinId, {
        transforms: [
          { translate: scaled(radial, explode * 16) },
          { rotate: { axis: Z_AXIS, origin: ORIGIN, angleDeg: carrierAngle } },
          { translate: [0, 0, -explode * 4] }
        ]
      });
    }
  }
};
