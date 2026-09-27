// Two joint values closer than this are the same value: below what a slider
// shows, above what float arithmetic leaves behind.
export const URDF_JOINT_VALUE_EPSILON = 0.001;

function normalizedJointValueEntries(values) {
  if (!values || typeof values !== "object") {
    return [];
  }
  return Object.entries(values)
    .map(([name, value]) => [String(name || "").trim(), Number.isFinite(Number(value)) ? Number(value) : 0])
    .filter(([name]) => name)
    .sort(([leftName], [rightName]) => leftName.localeCompare(rightName));
}

export function jointValueMapsClose(left, right, epsilon = URDF_JOINT_VALUE_EPSILON) {
  const leftEntries = normalizedJointValueEntries(left);
  const rightEntries = normalizedJointValueEntries(right);
  if (leftEntries.length !== rightEntries.length) {
    return false;
  }
  for (let index = 0; index < rightEntries.length; index += 1) {
    const [leftName, leftValue] = leftEntries[index];
    const [rightName, rightValue] = rightEntries[index];
    if (leftName !== rightName || Math.abs(leftValue - rightValue) > epsilon) {
      return false;
    }
  }
  return true;
}
