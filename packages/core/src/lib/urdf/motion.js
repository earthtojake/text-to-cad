import { buildDefaultUrdfJointValues } from "./kinematics.js";

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function isAngularJoint(joint) {
  const jointType = String(joint?.type || "fixed");
  return jointType === "continuous" || jointType === "revolute";
}

export function nativeJointValueToDisplay(joint, value) {
  const numericValue = toFiniteNumber(value, 0);
  return isAngularJoint(joint) ? (numericValue * 180) / Math.PI : numericValue;
}

/** An SRDF group state's joint values (radians and metres) as a pose (degrees and metres); unknown joints dropped. */
export function srdfGroupStateJointValuesToDisplay(urdfData, jointValuesByName) {
  if (!jointValuesByName || typeof jointValuesByName !== "object") {
    return {};
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  return Object.fromEntries(
    Object.entries(jointValuesByName)
      .map(([name, value]) => {
        const jointName = String(name || "").trim();
        const joint = jointByName.get(jointName);
        return jointName && joint ? [jointName, nativeJointValueToDisplay(joint, value)] : null;
      })
      .filter(Boolean)
  );
}

/** The joints the SRDF group state(s) named `home` set, merged in order, as a pose. */
export function srdfHomeGroupStateJointValuesToDisplay(urdfData) {
  const groupStates = Array.isArray(urdfData?.srdf?.groupStates)
    ? urdfData.srdf.groupStates
    : Array.isArray(urdfData?.motion?.groupStates)
      ? urdfData.motion.groupStates
      : [];
  return groupStates.reduce((homeValues, state) => {
    if (String(state?.name || "").trim().toLowerCase() !== "home") {
      return homeValues;
    }
    return {
      ...homeValues,
      ...srdfGroupStateJointValuesToDisplay(urdfData, state?.jointValuesByName || state?.jointValuesByNameRad)
    };
  }, {});
}

/**
 * The pose a robot OPENS in: every joint at its declared default, then the SRDF group
 * state(s) named `home`. The viewer opens a robot here and a snapshot renders one here
 * (with the joints a request names on top), so the two agree on what "at rest" shows.
 * Degrees, or metres for a prismatic joint.
 */
export function robotOpeningPose(description) {
  return { ...buildDefaultUrdfJointValues(description), ...srdfHomeGroupStateJointValuesToDisplay(description) };
}
