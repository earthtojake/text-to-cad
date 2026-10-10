const TEXT_TO_CAD_URDF_NAMESPACE = "https://text-to-cad.dev/urdf";
const ANGULAR_JOINT_TYPES = Object.freeze(["continuous", "revolute"]);
const INTERSECTION_TOLERANCE = 1e-12;
const AXIS_ALIGNMENT_TOLERANCE = 1e-9;
const GEOMETRY_ABSOLUTE_TOLERANCE_METERS = 1e-9;
const GEOMETRY_RELATIVE_TOLERANCE = 1e-8;
const JOINT_LIMIT_TOLERANCE_DEG = 1e-6;
const OPERATING_RANGE_SAMPLE_COUNT = 720;
const TWO_PI = 2 * Math.PI;
const ZERO_POSE_TOLERANCE_RAD = 1e-7;

function elementLocalName(element) {
  return String(element?.localName || element?.tagName || "").split(":").pop();
}

function fourBarElements(jointElement) {
  return Array.from(jointElement?.childNodes || []).filter(
    (node) => node?.nodeType === 1 && elementLocalName(node) === "four_bar"
  );
}

function requiredAttribute(element, name, context) {
  const value = String(element?.getAttribute(name) || "").trim();
  if (!value) {
    throw new Error(`${context} must declare ${name}`);
  }
  return value;
}

function finiteAttribute(element, name, context) {
  const value = Number(requiredAttribute(element, name, context));
  if (!Number.isFinite(value)) {
    throw new Error(`${context} ${name} must be finite`);
  }
  return value;
}

function positiveAttribute(element, name, context) {
  const value = finiteAttribute(element, name, context);
  if (value <= 0) {
    throw new Error(`${context} ${name} must be positive`);
  }
  return value;
}

function normalizeAngleRad(value) {
  const wrapped = ((value + Math.PI) % (2 * Math.PI) + (2 * Math.PI)) % (2 * Math.PI) - Math.PI;
  return wrapped === -Math.PI && value > 0 ? Math.PI : wrapped;
}

function outputPin(coupling, driverAngleRad) {
  const outputAngle = coupling.outputZero + driverAngleRad;
  return [
    coupling.groundLength + (coupling.outputLength * Math.cos(outputAngle)),
    coupling.outputLength * Math.sin(outputAngle)
  ];
}

function circleIntersectionPoints(coupling, driverAngleRad) {
  const [pinX, pinY] = outputPin(coupling, driverAngleRad);
  const centerDistance = Math.hypot(pinX, pinY);
  const minimumReach = Math.abs(coupling.inputLength - coupling.couplerLength);
  const maximumReach = coupling.inputLength + coupling.couplerLength;
  if (centerDistance <= INTERSECTION_TOLERANCE) {
    throw new Error("four-bar output pin coincides with the input pivot");
  }
  if (centerDistance < minimumReach - INTERSECTION_TOLERANCE || centerDistance > maximumReach + INTERSECTION_TOLERANCE) {
    throw new Error("four-bar lengths cannot close at the requested driver angle");
  }
  const along = (
    (coupling.inputLength ** 2) - (coupling.couplerLength ** 2) + (centerDistance ** 2)
  ) / (2 * centerDistance);
  const heightSquared = Math.max(0, (coupling.inputLength ** 2) - (along ** 2));
  const height = Math.sqrt(heightSquared);
  const unitX = pinX / centerDistance;
  const unitY = pinY / centerDistance;
  const baseX = along * unitX;
  const baseY = along * unitY;
  return [
    [baseX - (height * unitY), baseY + (height * unitX)],
    [baseX + (height * unitY), baseY - (height * unitX)]
  ];
}

function inputAngleCandidates(coupling, driverAngleRad) {
  return circleIntersectionPoints(coupling, driverAngleRad).map(
    ([x, y]) => Math.atan2(y, x)
  );
}

function configuredBranchIndex(coupling) {
  const candidates = inputAngleCandidates(coupling, 0);
  const errors = candidates.map(
    (angle) => Math.abs(normalizeAngleRad(angle - coupling.inputZero))
  );
  return errors[0] <= errors[1] ? 0 : 1;
}

function axisInParentFrame(joint) {
  const [x, y, z] = Array.isArray(joint?.axis) ? joint.axis : [];
  const transform = Array.isArray(joint?.originTransform) ? joint.originTransform : [];
  if (![x, y, z].every(Number.isFinite) || transform.length !== 16) {
    throw new Error(`URDF joint ${joint?.name || "(unnamed)"} has an invalid four-bar axis or origin`);
  }
  const transformed = [
    (transform[0] * x) + (transform[1] * y) + (transform[2] * z),
    (transform[4] * x) + (transform[5] * y) + (transform[6] * z),
    (transform[8] * x) + (transform[9] * y) + (transform[10] * z)
  ];
  const magnitude = Math.hypot(...transformed);
  if (magnitude <= INTERSECTION_TOLERANCE) {
    throw new Error(`URDF joint ${joint?.name || "(unnamed)"} has a zero-length four-bar axis`);
  }
  return transformed.map((component) => component / magnitude);
}

function jointOriginPosition(joint) {
  const transform = Array.isArray(joint?.originTransform) ? joint.originTransform : [];
  if (transform.length !== 16 || ![transform[3], transform[7], transform[11]].every(Number.isFinite)) {
    throw new Error(`URDF joint ${joint?.name || "(unnamed)"} has an invalid four-bar origin`);
  }
  return [transform[3], transform[7], transform[11]];
}

function geometryTolerance(...lengths) {
  return GEOMETRY_ABSOLUTE_TOLERANCE_METERS + (
    GEOMETRY_RELATIVE_TOLERANCE * Math.max(...lengths.map(Math.abs))
  );
}

function validateGroundPivotGeometry(dependentJoint, driverJoint, axis) {
  const inputPivot = jointOriginPosition(dependentJoint);
  const outputPivot = jointOriginPosition(driverJoint);
  const pivotDelta = outputPivot.map((component, index) => component - inputPivot[index]);
  const axialSeparation = pivotDelta.reduce(
    (sum, component, index) => sum + (component * axis[index]),
    0
  );
  const planarDelta = pivotDelta.map(
    (component, index) => component - (axialSeparation * axis[index])
  );
  const planarSeparation = Math.hypot(...planarDelta);
  const expectedLength = dependentJoint.mimic.groundLength;
  const tolerance = geometryTolerance(planarSeparation, expectedLength);
  if (Math.abs(axialSeparation) > tolerance) {
    throw new Error(`URDF four-bar pivots for ${dependentJoint.name} are not coplanar`);
  }
  if (Math.abs(planarSeparation - expectedLength) > tolerance) {
    throw new Error(
      `URDF four-bar joint ${dependentJoint.name} declares ground length ${expectedLength}, but its pivots are ${planarSeparation} metres apart`
    );
  }
}

function validateFourBarAxes(dependentJoint, driverJoint) {
  if (dependentJoint.parentLink !== driverJoint.parentLink) {
    throw new Error(
      `URDF four-bar joint ${dependentJoint.name} and driver ${driverJoint.name} must share one ground link`
    );
  }
  const dependentAxis = axisInParentFrame(dependentJoint);
  const driverAxis = axisInParentFrame(driverJoint);
  const alignment = dependentAxis.reduce(
    (sum, component, index) => sum + (component * driverAxis[index]),
    0
  );
  if (alignment < 1 - AXIS_ALIGNMENT_TOLERANCE) {
    throw new Error(
      `URDF four-bar joint ${dependentJoint.name} and driver ${driverJoint.name} must use parallel, same-direction axes`
    );
  }
  validateGroundPivotGeometry(dependentJoint, driverJoint, dependentAxis);
}

function driverAngleRangeRad(driverJoint) {
  const minimumDeg = Number(driverJoint?.minValueDeg);
  const maximumDeg = Number(driverJoint?.maxValueDeg);
  if (!Number.isFinite(minimumDeg) || !Number.isFinite(maximumDeg) || minimumDeg > maximumDeg) {
    throw new Error(`URDF four-bar driver ${driverJoint?.name || "(unnamed)"} must have a finite operating range`);
  }
  return [(minimumDeg * Math.PI) / 180, (maximumDeg * Math.PI) / 180];
}

function rangeContainsPeriodicAngle(minimum, maximum, target) {
  const firstPeriod = Math.ceil((minimum - target) / TWO_PI);
  return target + (firstPeriod * TWO_PI) <= maximum + INTERSECTION_TOLERANCE;
}

function cosineRange(minimum, maximum) {
  const endpointCosines = [Math.cos(minimum), Math.cos(maximum)];
  const minimumCosine = rangeContainsPeriodicAngle(minimum, maximum, Math.PI)
    ? -1
    : Math.min(...endpointCosines);
  const maximumCosine = rangeContainsPeriodicAngle(minimum, maximum, 0)
    ? 1
    : Math.max(...endpointCosines);
  return [minimumCosine, maximumCosine];
}

function validateFourBarReachability(coupling, driverJoint) {
  const [driverMinimum, driverMaximum] = driverAngleRangeRad(driverJoint);
  const [minimumCosine, maximumCosine] = cosineRange(
    coupling.outputZero + driverMinimum,
    coupling.outputZero + driverMaximum
  );
  const baseSquared = (coupling.groundLength ** 2) + (coupling.outputLength ** 2);
  const cosineScale = 2 * coupling.groundLength * coupling.outputLength;
  const minimumCenterDistance = Math.sqrt(Math.max(0, baseSquared + (cosineScale * minimumCosine)));
  const maximumCenterDistance = Math.sqrt(Math.max(0, baseSquared + (cosineScale * maximumCosine)));
  const minimumReach = Math.abs(coupling.inputLength - coupling.couplerLength);
  const maximumReach = coupling.inputLength + coupling.couplerLength;
  if (
    minimumCenterDistance <= INTERSECTION_TOLERANCE
    || minimumCenterDistance < minimumReach - INTERSECTION_TOLERANCE
    || maximumCenterDistance > maximumReach + INTERSECTION_TOLERANCE
  ) {
    throw new Error(`URDF four-bar driver ${driverJoint.name} includes angles where the linkage cannot close`);
  }
}

function sampledDriverAnglesRad(driverJoint) {
  const [minimum, maximum] = driverAngleRangeRad(driverJoint);
  return Array.from(
    { length: OPERATING_RANGE_SAMPLE_COUNT + 1 },
    (_, index) => minimum + (((maximum - minimum) * index) / OPERATING_RANGE_SAMPLE_COUNT)
  );
}

function validateFourBarOperatingRange(dependentJoint, driverJoint) {
  const derivedValuesDeg = sampledDriverAnglesRad(driverJoint).map((driverAngleRad) => {
    try {
      return (solveFourBarCoupling(dependentJoint.mimic, driverAngleRad) * 180) / Math.PI;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(
        `URDF four-bar joint ${dependentJoint.name} cannot close at driver angle ${(driverAngleRad * 180) / Math.PI} degrees: ${message}`
      );
    }
  });
  if (String(dependentJoint.type) === "continuous") {
    return;
  }
  const derivedMinimumDeg = Math.min(...derivedValuesDeg);
  const derivedMaximumDeg = Math.max(...derivedValuesDeg);
  if (
    derivedMinimumDeg < dependentJoint.minValueDeg - JOINT_LIMIT_TOLERANCE_DEG
    || derivedMaximumDeg > dependentJoint.maxValueDeg + JOINT_LIMIT_TOLERANCE_DEG
  ) {
    throw new Error(
      `URDF four-bar joint ${dependentJoint.name} derives ${derivedMinimumDeg} to ${derivedMaximumDeg} degrees outside its limits`
    );
  }
}

export function solveFourBarCoupling(coupling, driverAngleRad) {
  if (!Number.isFinite(driverAngleRad)) {
    throw new Error("four-bar driver angle must be finite");
  }
  const candidates = inputAngleCandidates(coupling, driverAngleRad);
  const branchIndex = coupling.branchIndex === 1 ? 1 : 0;
  const inputAngle = candidates[branchIndex];
  return normalizeAngleRad(inputAngle - coupling.inputZero);
}

export function parseFourBarCoupling(jointElement, jointName) {
  const elements = fourBarElements(jointElement);
  if (!elements.length) {
    return null;
  }
  if (elements.length !== 1) {
    throw new Error(`URDF joint ${jointName} must declare at most one tcad:four_bar element`);
  }
  const element = elements[0];
  if (element.namespaceURI !== TEXT_TO_CAD_URDF_NAMESPACE) {
    throw new Error(`URDF joint ${jointName} tcad:four_bar must use namespace ${TEXT_TO_CAD_URDF_NAMESPACE}`);
  }
  const context = `URDF four-bar joint ${jointName}`;
  const geometry = {
    kind: "fourBar",
    joint: requiredAttribute(element, "driver", context),
    inputLength: positiveAttribute(element, "input_length", context),
    groundLength: positiveAttribute(element, "ground_length", context),
    outputLength: positiveAttribute(element, "output_length", context),
    couplerLength: positiveAttribute(element, "coupler_length", context),
    inputZero: finiteAttribute(element, "input_zero", context),
    outputZero: finiteAttribute(element, "output_zero", context)
  };
  const coupling = {
    ...geometry,
    branchIndex: configuredBranchIndex(geometry)
  };
  if (Math.abs(solveFourBarCoupling(coupling, 0)) > ZERO_POSE_TOLERANCE_RAD) {
    throw new Error(`${context} zero angles do not describe the selected assembly branch`);
  }
  return coupling;
}

export function validateFourBarJointConfiguration(dependentJoint, driverJoint) {
  if (dependentJoint?.mimic?.kind !== "fourBar") {
    return;
  }
  if (!ANGULAR_JOINT_TYPES.includes(String(dependentJoint?.type || ""))) {
    throw new Error(`URDF four-bar joint ${dependentJoint?.name || "(unnamed)"} must be revolute or continuous`);
  }
  if (!ANGULAR_JOINT_TYPES.includes(String(driverJoint?.type || ""))) {
    throw new Error(`URDF four-bar driver ${driverJoint?.name || "(missing)"} must be revolute or continuous`);
  }
  validateFourBarAxes(dependentJoint, driverJoint);
  validateFourBarReachability(dependentJoint.mimic, driverJoint);
  validateFourBarOperatingRange(dependentJoint, driverJoint);
}
