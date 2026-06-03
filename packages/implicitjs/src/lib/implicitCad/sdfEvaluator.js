function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isVector(value) {
  return Array.isArray(value);
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function truthy(value) {
  if (isVector(value)) {
    return value.some((component) => truthy(component));
  }
  return Boolean(value);
}

function vec(args, size) {
  const flat = [];
  for (const arg of args) {
    if (isVector(arg)) {
      flat.push(...arg);
    } else {
      flat.push(arg);
    }
  }
  if (flat.length === 0) {
    flat.push(0);
  }
  if (flat.length === 1) {
    return Array.from({ length: size }, () => finiteNumber(flat[0]));
  }
  return Array.from({ length: size }, (_, index) => finiteNumber(flat[index], 0));
}

function vec2(x = 0, y = undefined) {
  return vec(y === undefined ? [x] : [x, y], 2);
}

function vec3(x = 0, y = undefined, z = undefined) {
  return vec(y === undefined && z === undefined ? [x] : [x, y, z], 3);
}

function vec4(x = 0, y = undefined, z = undefined, w = undefined) {
  return vec(y === undefined && z === undefined && w === undefined ? [x] : [x, y, z, w], 4);
}

function mapUnary(value, fn) {
  return isVector(value) ? value.map((component) => fn(component)) : fn(value);
}

function mapBinary(a, b, fn) {
  if (isVector(a) && isVector(b)) {
    const size = Math.max(a.length, b.length);
    return Array.from({ length: size }, (_, index) => fn(a[index] ?? 0, b[index] ?? 0));
  }
  if (isVector(a)) {
    return a.map((component) => fn(component, b));
  }
  if (isVector(b)) {
    return b.map((component) => fn(a, component));
  }
  return fn(a, b);
}

function add(a, b) {
  return mapBinary(a, b, (x, y) => x + y);
}

function sub(a, b) {
  return mapBinary(a, b, (x, y) => x - y);
}

function mul(a, b) {
  return mapBinary(a, b, (x, y) => x * y);
}

function div(a, b) {
  return mapBinary(a, b, (x, y) => x / y);
}

function neg(value) {
  return mapUnary(value, (component) => -component);
}

function abs(value) {
  return mapUnary(value, Math.abs);
}

function minValue(a, b) {
  return mapBinary(a, b, Math.min);
}

function maxValue(a, b) {
  return mapBinary(a, b, Math.max);
}

function clamp(value, low, high) {
  return minValue(maxValue(value, low), high);
}

function mix(a, b, t) {
  return add(mul(a, sub(1, t)), mul(b, t));
}

function smoothstep(edge0, edge1, value) {
  const t = clamp(div(sub(value, edge0), sub(edge1, edge0)), 0, 1);
  return mul(mul(t, t), sub(3, mul(2, t)));
}

function mod(a, b) {
  return mapBinary(a, b, (x, y) => x - y * Math.floor(x / y));
}

function length(value) {
  if (!isVector(value)) {
    return Math.abs(value);
  }
  return Math.hypot(...value);
}

function dot(a, b) {
  const va = isVector(a) ? a : [a];
  const vb = isVector(b) ? b : [b];
  const size = Math.max(va.length, vb.length);
  let sum = 0;
  for (let index = 0; index < size; index += 1) {
    sum += (va[index] ?? 0) * (vb[index] ?? 0);
  }
  return sum;
}

function cross(a, b) {
  const va = vec3(a);
  const vb = vec3(b);
  return [
    va[1] * vb[2] - va[2] * vb[1],
    va[2] * vb[0] - va[0] * vb[2],
    va[0] * vb[1] - va[1] * vb[0],
  ];
}

function normalize(value) {
  const len = length(value);
  return len > 1e-12 ? div(value, len) : mul(value, 0);
}

function swizzleIndices(swizzle) {
  const lookup = {
    x: 0, y: 1, z: 2, w: 3,
    r: 0, g: 1, b: 2, a: 3,
    s: 0, t: 1, p: 2, q: 3,
  };
  return String(swizzle || "").split("").map((component) => lookup[component]);
}

function getSwizzle(value, swizzle) {
  const indices = swizzleIndices(swizzle);
  if (!indices.length || indices.some((index) => index === undefined)) {
    throw new Error(`Unsupported GLSL member access: .${swizzle}`);
  }
  const source = isVector(value) ? value : [value];
  const result = indices.map((index) => source[index] ?? 0);
  return result.length === 1 ? result[0] : result;
}

function setSwizzle(target, swizzle, value) {
  if (!isVector(target)) {
    throw new Error(`Cannot assign .${swizzle} on a scalar value`);
  }
  const indices = swizzleIndices(swizzle);
  const values = isVector(value) ? value : [value];
  indices.forEach((targetIndex, index) => {
    if (targetIndex === undefined) {
      throw new Error(`Unsupported GLSL member assignment: .${swizzle}`);
    }
    target[targetIndex] = finiteNumber(values[index], values[0] ?? 0);
  });
  return target;
}

function implicit_linear_map(value, inMin, inMax, outMin, outMax) {
  const slope = (outMax - outMin) / (inMax - inMin);
  return (value - inMin) * slope + outMin;
}

function implicit_ramp(value, inMin, inMax, outMin, outMax) {
  return Math.min(Math.max(implicit_linear_map(value, inMin, inMax, outMin, outMax), outMin), outMax);
}

function implicit_two_body_field(a, b) {
  return (a - b) / (a + b);
}

function implicit_two_body_polar(a, b, angle) {
  return a * Math.cos(angle) + b * Math.sin(angle);
}

function implicit_triangle_wave_even(value, period) {
  if (isVector(value) || isVector(period)) {
    return mapBinary(value, period, implicit_triangle_wave_even);
  }
  const halfPeriod = period * 0.5;
  const quarterPeriod = period * 0.25;
  const wrapped = mod(value + halfPeriod, period);
  return quarterPeriod - Math.abs(wrapped - halfPeriod);
}

function implicit_triangle_wave_even_positive(value, period) {
  return add(implicit_triangle_wave_even(value, period), mul(period, 0.25));
}

function implicit_triangle_wave_odd(value, period) {
  return implicit_triangle_wave_even(sub(value, mul(period, 0.5)), period);
}

function implicit_triangle_wave_odd_positive(value, period) {
  return add(implicit_triangle_wave_odd(value, period), mul(period, 0.25));
}

function implicit_repeat_centered(p, period) {
  return sub(mod(add(p, mul(period, 0.5)), period), mul(period, 0.5));
}

function implicit_intersect_round(a, b, radius) {
  const k = Math.max(radius, 0);
  const q = maxValue(add(vec2(a, b), k), 0);
  return Math.min(-k, Math.max(a, b)) + length(q);
}

function implicit_intersect_chamfer(a, b, radius) {
  return Math.max(Math.max(a, b), (a + b + radius) * 0.7071067811865476);
}

function implicit_intersect_exp(a, b, radius) {
  const k = Math.max(radius, 1e-6) * 0.5;
  return k * Math.log(Math.exp(a / k) + Math.exp(b / k));
}

function implicit_intersect_lp_norm(a, b, radius, normPower) {
  const k = Math.max(radius, 0);
  const p = Math.max(normPower, 1e-6);
  const q = maxValue(add(vec2(a, b), k), 0);
  return Math.min(-k, Math.max(a, b)) + Math.pow(Math.pow(q[0], p) + Math.pow(q[1], p), 1 / p);
}

function implicit_intersect_rvachev(a, b, radius) {
  const sharp = Math.max(a, b);
  const k = Math.max(radius, 0);
  if (k <= 0) {
    return sharp;
  }
  const r0 = a + b - Math.sqrt(a * a + b * b);
  const t = Math.min(Math.max((sharp + k) / k, 0), 1);
  const s = t * t * (3 - 2 * t);
  return sharp < -k ? sharp : mix(sharp, r0, s);
}

const BUILTINS = {
  float: (value = 0) => finiteNumber(value),
  int: (value = 0) => Math.trunc(finiteNumber(value)),
  bool: (value = false) => truthy(value),
  vec2,
  vec3,
  vec4,
  abs,
  min: minValue,
  max: maxValue,
  clamp,
  mix,
  smoothstep,
  mod,
  length,
  dot,
  cross,
  normalize,
  sin: (value) => mapUnary(value, Math.sin),
  cos: (value) => mapUnary(value, Math.cos),
  tan: (value) => mapUnary(value, Math.tan),
  atan: (...args) => args.length >= 2 ? Math.atan2(args[0], args[1]) : mapUnary(args[0], Math.atan),
  pow: (a, b) => mapBinary(a, b, Math.pow),
  sqrt: (value) => mapUnary(value, Math.sqrt),
  exp: (value) => mapUnary(value, Math.exp),
  log: (value) => mapUnary(value, Math.log),
  floor: (value) => mapUnary(value, Math.floor),
  ceil: (value) => mapUnary(value, Math.ceil),
  fract: (value) => mapUnary(value, (component) => component - Math.floor(component)),
  sign: (value) => mapUnary(value, Math.sign),

  implicit_clamp01: (value) => clamp(value, 0, 1),
  implicit_linear_map,
  implicit_ramp,
  implicit_two_body_field,
  implicit_two_body_polar,
  implicit_triangle_wave_even,
  implicit_triangle_wave_even_positive,
  implicit_triangle_wave_odd,
  implicit_triangle_wave_odd_positive,
  implicit_repeat_centered,
  implicit_intersect_sharp: (a, b) => Math.max(a, b),
  implicit_union_sharp: (a, b) => Math.min(a, b),
  implicit_intersect_round,
  implicit_union_round: (a, b, radius) => -implicit_intersect_round(-a, -b, radius),
  implicit_intersect_chamfer,
  implicit_union_chamfer: (a, b, radius) => -implicit_intersect_chamfer(-a, -b, radius),
  implicit_intersect_exp,
  implicit_union_exp: (a, b, radius) => -implicit_intersect_exp(-a, -b, radius),
  implicit_intersect_lp_norm,
  implicit_union_lp_norm: (a, b, radius, normPower) => -implicit_intersect_lp_norm(-a, -b, radius, normPower),
  implicit_intersect_rvachev,
  implicit_union_rvachev: (a, b, radius) => -implicit_intersect_rvachev(-a, -b, radius),
  implicit_plane2: (p, origin, normal) => dot(sub(p, origin), normalize(normal)),
  implicit_line_segment2: (p, a, b) => {
    const segment = sub(b, a);
    const segmentLengthSq = dot(segment, segment);
    if (segmentLengthSq < 1e-12) {
      return length(sub(p, a));
    }
    const t = clamp(dot(sub(p, a), segment) / segmentLengthSq, 0, 1);
    return length(sub(p, add(a, mul(t, segment))));
  },
  implicit_sphere: (p, center, radius) => length(sub(p, center)) - radius,
  implicit_box_centered: (p, size, center) => {
    const q = sub(abs(sub(p, center)), mul(size, 0.5));
    return length(maxValue(q, 0)) + Math.min(Math.max(q[0], Math.max(q[1], q[2])), 0);
  },
  implicit_plane: (p, origin, normal) => dot(sub(p, origin), normalize(normal)),
  implicit_line_segment: (p, a, b) => {
    const segment = sub(b, a);
    const segmentLengthSq = dot(segment, segment);
    if (segmentLengthSq < 1e-12) {
      return length(sub(p, a));
    }
    const t = clamp(dot(sub(p, a), segment) / segmentLengthSq, 0, 1);
    return length(sub(p, add(a, mul(t, segment))));
  },
  implicit_torus: (p, majorRadius, minorRadius) => {
    const q = vec2(length(getSwizzle(p, "xy")) - majorRadius, getSwizzle(p, "z"));
    return length(q) - minorRadius;
  },
  implicit_axis: (p, origin, direction) => {
    const directionLength = length(direction);
    if (directionLength < 1e-12) {
      return length(sub(p, origin));
    }
    const axis = div(direction, directionLength);
    const toPoint = sub(p, origin);
    return length(sub(toPoint, mul(dot(toPoint, axis), axis)));
  },
  implicit_cylinder: (p, origin, direction, radius) => BUILTINS.implicit_axis(p, origin, direction) - radius,
  implicit_cylinder_capped: (p, a, b, radius) => {
    const axis = sub(b, a);
    const side = BUILTINS.implicit_cylinder(p, a, axis, radius);
    const capA = -BUILTINS.implicit_plane(p, a, axis);
    const capB = BUILTINS.implicit_plane(p, b, axis);
    return Math.max(side, Math.max(capA, capB));
  },
  implicit_capsule: (p, a, b, radius) => BUILTINS.implicit_line_segment(p, a, b) - radius,
  implicit_cone_capsule: (p, a, b, radiusA, radiusB) => {
    const axis = sub(b, a);
    const axisLengthSq = dot(axis, axis);
    if (axisLengthSq < 1e-12) {
      return BUILTINS.implicit_sphere(p, a, radiusA);
    }
    const t = clamp(dot(sub(p, a), axis) / axisLengthSq, 0, 1);
    const radius = mix(radiusA, radiusB, t);
    return length(sub(p, add(a, mul(t, axis)))) - radius;
  },
  implicit_cone: (p, apex, direction, halfAngle) => {
    const directionLength = length(direction);
    if (directionLength < 1e-12) {
      return length(sub(p, apex));
    }
    const axis = div(direction, directionLength);
    const toPoint = sub(p, apex);
    const axial = dot(toPoint, axis);
    const perpendicular = length(sub(toPoint, mul(axial, axis)));
    return perpendicular - axial * Math.tan(halfAngle);
  },
  implicit_cone_capped: (p, a, b, radiusA, radiusB) => {
    const axis = sub(b, a);
    const axisLength = length(axis);
    if (axisLength < 1e-12) {
      return BUILTINS.implicit_sphere(p, a, radiusA);
    }
    const halfAngle = Math.atan2(Math.abs(radiusB - radiusA), axisLength);
    const coneDistance = radiusA < radiusB
      ? BUILTINS.implicit_cone(p, a, axis, halfAngle) - radiusA
      : BUILTINS.implicit_cone(p, b, neg(axis), halfAngle) - radiusB;
    const capA = -BUILTINS.implicit_plane(p, a, axis);
    const capB = BUILTINS.implicit_plane(p, b, axis);
    return Math.max(coneDistance, Math.max(capA, capB));
  },
  implicit_shell: (distanceValue, thickness, bias = 0) => Math.abs(distanceValue + bias * thickness * 0.5) - thickness * 0.5,
  implicit_rotate_axis: (p, origin, direction, angle) => {
    const k = normalize(direction);
    const local = sub(p, origin);
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    return add(add(add(origin, mul(local, c)), mul(cross(k, local), s)), mul(k, dot(k, local) * (1 - c)));
  },
  implicit_remap_cylindrical: (p, circumference) => {
    const radial = length(getSwizzle(p, "xy"));
    const theta = Math.atan2(p[1], p[0]);
    return vec3(radial, theta * (circumference / (Math.PI * 2)), p[2]);
  },
  implicit_tpms_gyroid: (p, period, drop) => {
    const xyz = mul(p, div(Math.PI * 2, period));
    const yzx = getSwizzle(xyz, "yzx");
    const field = dot(drop, mul(BUILTINS.sin(xyz), BUILTINS.cos(yzx)));
    return field * (period[0] + period[1] + period[2]) / 18;
  },
  implicit_tpms_schwarz: (p, period, drop, gyroidBlend) => {
    const xyz = mul(p, div(Math.PI * 2, period));
    const yzx = getSwizzle(xyz, "yzx");
    const mixTerm = add(vec3(-(1 - gyroidBlend)), mul(BUILTINS.sin(xyz), gyroidBlend));
    const field = dot(drop, mul(BUILTINS.cos(yzx), mixTerm));
    return field * (period[0] + period[1] + period[2]) / 36;
  },
  implicit_diamond: () => 0,
};

BUILTINS.implicit_tpms_diamond = (p, period, drop, gyroidBlend) => {
  const xyz = mul(p, div(Math.PI * 2, period));
  const yzx = getSwizzle(xyz, "yzx");
  const zxy = getSwizzle(xyz, "zxy");
  const sinXyz = BUILTINS.sin(xyz);
  const cosYzx = BUILTINS.cos(yzx);
  const cosZxy = BUILTINS.cos(zxy);
  const blendFactor = 1 - gyroidBlend;
  const term1 = blendFactor * sinXyz[0] * sinXyz[1] * sinXyz[2];
  const term2 = dot(drop, mul(mul(sinXyz, cosYzx), add(mul(cosZxy, blendFactor), vec3(gyroidBlend))));
  return (term1 + term2) * (period[0] + period[1] + period[2]) / (6 * 2.8284271247461903 * 2);
};

BUILTINS.implicit_tpms_lidinoid = (p, period, drop, gyroidBlend) => {
  const xyz = mul(p, div(Math.PI * 2, period));
  const yzx = getSwizzle(xyz, "yzx");
  const zxy = getSwizzle(xyz, "zxy");
  const cos2Xyz = BUILTINS.cos(mul(2, xyz));
  const cos2Yzx = getSwizzle(cos2Xyz, "yzx");
  const blendFactor = 1 - gyroidBlend;
  const term1 = dot(drop, mul(mul(BUILTINS.sin(zxy), BUILTINS.cos(yzx)), add(mul(BUILTINS.sin(mul(2, xyz)), blendFactor), vec3(gyroidBlend))));
  const term2 = blendFactor * dot(cos2Xyz, cos2Yzx);
  return (term1 - term2) * (period[0] + period[1] + period[2]) / 72;
};

BUILTINS.implicit_tpms_neovius = (p, period, drop, schwarzBlend) => {
  const xyz = mul(p, div(Math.PI * 2, period));
  const cosDrop = mul(BUILTINS.cos(xyz), drop);
  const term1 = -dot(cosDrop, vec3(1));
  const term2 = (1 - schwarzBlend) * (4 / 3) * cosDrop[0] * cosDrop[1] * cosDrop[2];
  return (term1 - term2) * (period[0] + period[1] + period[2]) / (6 * (26 / 3));
};

BUILTINS.implicit_tpms_split_p = (p, period, lidinoidBlend, gyroidOctave, schwarzOctave) => {
  const xyz = mul(p, div(Math.PI * 2, period));
  const yzx = getSwizzle(xyz, "yzx");
  const zxy = getSwizzle(xyz, "zxy");
  const sin2Xyz = BUILTINS.sin(mul(2, xyz));
  const cos2Xyz = BUILTINS.cos(mul(2, xyz));
  const term1 = -lidinoidBlend * dot(mul(mul(sin2Xyz, BUILTINS.cos(yzx)), BUILTINS.sin(zxy)), vec3(1));
  const term2 = gyroidOctave * dot(mul(sin2Xyz, cos2Xyz), vec3(1));
  const term3 = schwarzOctave * dot(cos2Xyz, vec3(1));
  return (term1 + term2 + term3) * (period[0] + period[1] + period[2]) / 36;
};

BUILTINS.implicit_tpms_iwp = (p, period, drop) => {
  const xyz = mul(p, div(Math.PI * 2, period));
  const yzx = getSwizzle(xyz, "yzx");
  const term1 = 2 * dot(mul(mul(drop, BUILTINS.cos(xyz)), BUILTINS.cos(yzx)), vec3(1));
  const term2 = dot(BUILTINS.cos(mul(2, xyz)), vec3(1));
  return (term1 - term2) * (period[0] + period[1] + period[2]) / 48;
};

BUILTINS.implicit_cubic_grid = (p, size) => {
  const d = implicit_triangle_wave_even_positive(p, size);
  return Math.min(d[0], Math.min(d[1], d[2]));
};

BUILTINS.implicit_square_honeycomb = (p, size) => {
  const d = implicit_triangle_wave_even_positive(getSwizzle(p, "xy"), size);
  return Math.min(d[0], d[1]);
};

BUILTINS.implicit_square_honeycomb_reinforced = (p, size, rotation, rotation2, hasRotation2) => {
  const pxy = getSwizzle(p, "xy");
  const grid = implicit_triangle_wave_even_positive(pxy, size);
  const squareGrid = Math.min(grid[0], grid[1]);
  const repeated = implicit_repeat_centered(pxy, size);
  const angle = Math.PI * rotation;
  let diagonal = Math.abs(BUILTINS.implicit_plane2(repeated, vec2(0), vec2(Math.cos(angle), Math.sin(angle))));
  if (hasRotation2 > 0.5) {
    const angle2 = Math.PI * rotation2;
    const diagonal2 = Math.abs(BUILTINS.implicit_plane2(repeated, vec2(0), vec2(Math.cos(angle2), Math.sin(angle2))));
    diagonal = Math.min(diagonal, diagonal2);
  }
  return Math.min(squareGrid, diagonal);
};

BUILTINS.implicit_square_diagonal_honeycomb = (p, size) => {
  const period = vec2(size[0] + size[1]);
  const repeated = implicit_repeat_centered(getSwizzle(p, "xy"), period);
  const positive = Math.abs(BUILTINS.implicit_plane2(repeated, vec2(0), vec2(size[1], size[0])));
  const negative = Math.abs(BUILTINS.implicit_plane2(repeated, vec2(0), vec2(size[1], -size[0])));
  return Math.min(positive, negative);
};

BUILTINS.implicit_octet_honeycomb = (p, size) => {
  const pxy = getSwizzle(p, "xy");
  const square = BUILTINS.implicit_square_honeycomb(p, size);
  const oddGrid = implicit_triangle_wave_odd_positive(pxy, size);
  const planeGrid = Math.min(oddGrid[0], oddGrid[1]);
  const diagonalPeriod = length(size) * 0.5;
  const rotated = vec2((pxy[0] + pxy[1]) / 1.4142135623730951, (pxy[0] - pxy[1]) / 1.4142135623730951);
  const diagonal = implicit_triangle_wave_odd_positive(rotated, vec2(diagonalPeriod));
  return Math.min(Math.min(square, planeGrid), Math.min(diagonal[0], diagonal[1]));
};

BUILTINS.implicit_hexagonal_honeycomb = (p, size, setback) => {
  const pxy = getSwizzle(p, "xy");
  const halfSize = mul(size, 0.5);
  const quarterSize = mul(size, 0.25);
  const starCenter = vec2(0, (1 - setback) * halfSize[1]);
  const transition = vec2(halfSize[0], setback * halfSize[1]);
  const folded = abs(implicit_repeat_centered(pxy, size));
  const reflected = vec2(folded[0] - halfSize[0], halfSize[1] - folded[1]);
  const foldedStar = Math.min(
    BUILTINS.implicit_line_segment2(folded, starCenter, vec2(0, size[1])),
    Math.min(
      BUILTINS.implicit_line_segment2(folded, starCenter, transition),
      BUILTINS.implicit_line_segment2(folded, starCenter, vec2(-transition[0], transition[1]))
    )
  );
  const reflectedStar = Math.min(
    BUILTINS.implicit_line_segment2(reflected, starCenter, vec2(0, size[1])),
    Math.min(
      BUILTINS.implicit_line_segment2(reflected, starCenter, transition),
      BUILTINS.implicit_line_segment2(reflected, starCenter, vec2(-transition[0], transition[1]))
    )
  );
  return folded[0] < quarterSize[0] ? foldedStar : reflectedStar;
};

BUILTINS.implicit_triangular_honeycomb = (p, size) => {
  const folded = abs(implicit_repeat_centered(getSwizzle(p, "xy"), size));
  const halfSize = mul(size, 0.5);
  const quarterSize = mul(size, 0.25);
  const normalH = vec2(0, 1);
  const normalP60 = normalize(vec2(size[1], size[0]));
  const normalN60 = normalize(vec2(size[1], -size[0]));
  const foldedStar = Math.min(
    Math.abs(dot(folded, normalH)),
    Math.min(Math.abs(dot(folded, normalP60)), Math.abs(dot(folded, normalN60)))
  );
  const shifted = sub(folded, halfSize);
  const shiftedStar = Math.min(
    Math.abs(dot(shifted, normalH)),
    Math.min(Math.abs(dot(shifted, normalP60)), Math.abs(dot(shifted, normalN60)))
  );
  return folded[1] < quarterSize[1] ? foldedStar : shiftedStar;
};

const TYPE_KEYWORDS = new Set(["float", "int", "bool", "vec2", "vec3", "vec4"]);
const QUALIFIERS = new Set(["const", "highp", "mediump", "lowp", "in", "out", "uniform", "varying"]);
const OPERATORS = ["<=", ">=", "==", "!=", "&&", "||", "+=", "-=", "*=", "/=", "++", "--"];

function stripComments(source) {
  return String(source || "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

function tokenize(source) {
  const tokens = [];
  const text = stripComments(source);
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (/\s/.test(char)) {
      index += 1;
      continue;
    }
    const numberMatch = text.slice(index).match(/^(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?/);
    if (numberMatch) {
      tokens.push({ type: "number", value: Number(numberMatch[0]) });
      index += numberMatch[0].length;
      continue;
    }
    const identifierMatch = text.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (identifierMatch) {
      tokens.push({ type: "identifier", value: identifierMatch[0] });
      index += identifierMatch[0].length;
      continue;
    }
    const op = OPERATORS.find((candidate) => text.startsWith(candidate, index));
    if (op) {
      tokens.push({ type: "operator", value: op });
      index += op.length;
      continue;
    }
    tokens.push({ type: "punct", value: char });
    index += 1;
  }
  return tokens;
}

class Parser {
  constructor(tokens) {
    this.tokens = tokens;
    this.index = 0;
  }

  peek(offset = 0) {
    return this.tokens[this.index + offset] || null;
  }

  consume(value = null) {
    const token = this.peek();
    if (!token) {
      throw new Error(`Expected ${value || "token"}, reached end of GLSL source`);
    }
    if (value !== null && token.value !== value) {
      throw new Error(`Expected ${value}, got ${token.value}`);
    }
    this.index += 1;
    return token;
  }

  match(value) {
    if (this.peek()?.value === value) {
      this.index += 1;
      return true;
    }
    return false;
  }

  skipQualifiers() {
    while (QUALIFIERS.has(this.peek()?.value)) {
      this.consume();
    }
  }

  parseProgram() {
    const globals = [];
    const functions = new Map();
    while (this.peek()) {
      this.skipQualifiers();
      const type = this.peek()?.value;
      if (!TYPE_KEYWORDS.has(type) && type !== "void") {
        this.consume();
        continue;
      }
      this.consume();
      const name = this.consume().value;
      if (this.match("(")) {
        const params = [];
        if (!this.match(")")) {
          do {
            this.skipQualifiers();
            const paramType = this.consume().value;
            const paramName = this.consume().value;
            params.push({ type: paramType, name: paramName });
          } while (this.match(","));
          this.consume(")");
        }
        functions.set(name, {
          name,
          params,
          returnType: type,
          body: this.parseBlock()
        });
      } else {
        let init = { type: "literal", value: 0 };
        if (this.match("=")) {
          init = this.parseExpression();
        }
        this.consume(";");
        globals.push({ type: "var", varType: type, name, init });
      }
    }
    return { globals, functions };
  }

  parseBlock() {
    this.consume("{");
    const body = [];
    while (this.peek() && this.peek().value !== "}") {
      body.push(this.parseStatement());
    }
    this.consume("}");
    return { type: "block", body };
  }

  parseStatement() {
    if (this.peek()?.value === "{") {
      return this.parseBlock();
    }
    if (this.match(";")) {
      return { type: "empty" };
    }
    if (this.match("return")) {
      const expression = this.parseExpression();
      this.consume(";");
      return { type: "return", expression };
    }
    if (this.match("if")) {
      this.consume("(");
      const condition = this.parseExpression();
      this.consume(")");
      const consequent = this.parseStatement();
      const alternate = this.match("else") ? this.parseStatement() : null;
      return { type: "if", condition, consequent, alternate };
    }
    if (this.match("for")) {
      this.consume("(");
      const init = this.parseForPart(";");
      this.consume(";");
      const condition = this.peek()?.value === ";" ? null : this.parseExpression();
      this.consume(";");
      const update = this.peek()?.value === ")" ? null : this.parseExpression();
      this.consume(")");
      return { type: "for", init, condition, update, body: this.parseStatement() };
    }
    if (TYPE_KEYWORDS.has(this.peek()?.value) || (QUALIFIERS.has(this.peek()?.value) && TYPE_KEYWORDS.has(this.peek(1)?.value))) {
      const statement = this.parseVariableDeclaration();
      this.consume(";");
      return statement;
    }
    const expression = this.parseExpression();
    this.consume(";");
    return { type: "expr", expression };
  }

  parseForPart() {
    if (TYPE_KEYWORDS.has(this.peek()?.value) || (QUALIFIERS.has(this.peek()?.value) && TYPE_KEYWORDS.has(this.peek(1)?.value))) {
      return this.parseVariableDeclaration();
    }
    if (this.peek()?.value === ";") {
      return { type: "empty" };
    }
    return { type: "expr", expression: this.parseExpression() };
  }

  parseVariableDeclaration() {
    this.skipQualifiers();
    const varType = this.consume().value;
    const name = this.consume().value;
    let init = { type: "literal", value: defaultValueForType(varType) };
    if (this.match("=")) {
      init = this.parseExpression();
    }
    return { type: "var", varType, name, init };
  }

  parseExpression() {
    return this.parseAssignment();
  }

  parseAssignment() {
    const left = this.parseTernary();
    const op = this.peek()?.value;
    if (["=", "+=", "-=", "*=", "/="].includes(op)) {
      this.consume();
      return { type: "assign", op, left, right: this.parseAssignment() };
    }
    return left;
  }

  parseTernary() {
    const condition = this.parseLogicalOr();
    if (!this.match("?")) {
      return condition;
    }
    const consequent = this.parseExpression();
    this.consume(":");
    return { type: "ternary", condition, consequent, alternate: this.parseExpression() };
  }

  parseLogicalOr() {
    let node = this.parseLogicalAnd();
    while (this.match("||")) {
      node = { type: "binary", op: "||", left: node, right: this.parseLogicalAnd() };
    }
    return node;
  }

  parseLogicalAnd() {
    let node = this.parseEquality();
    while (this.match("&&")) {
      node = { type: "binary", op: "&&", left: node, right: this.parseEquality() };
    }
    return node;
  }

  parseEquality() {
    let node = this.parseComparison();
    while (["==", "!="].includes(this.peek()?.value)) {
      const op = this.consume().value;
      node = { type: "binary", op, left: node, right: this.parseComparison() };
    }
    return node;
  }

  parseComparison() {
    let node = this.parseAdditive();
    while (["<", ">", "<=", ">="].includes(this.peek()?.value)) {
      const op = this.consume().value;
      node = { type: "binary", op, left: node, right: this.parseAdditive() };
    }
    return node;
  }

  parseAdditive() {
    let node = this.parseMultiplicative();
    while (["+", "-"].includes(this.peek()?.value)) {
      const op = this.consume().value;
      node = { type: "binary", op, left: node, right: this.parseMultiplicative() };
    }
    return node;
  }

  parseMultiplicative() {
    let node = this.parseUnary();
    while (["*", "/"].includes(this.peek()?.value)) {
      const op = this.consume().value;
      node = { type: "binary", op, left: node, right: this.parseUnary() };
    }
    return node;
  }

  parseUnary() {
    if (this.match("+")) {
      return this.parseUnary();
    }
    if (this.match("-")) {
      return { type: "unary", op: "-", argument: this.parseUnary() };
    }
    if (this.match("!")) {
      return { type: "unary", op: "!", argument: this.parseUnary() };
    }
    if (this.match("++")) {
      return { type: "update", op: "++", argument: this.parseUnary(), prefix: true };
    }
    if (this.match("--")) {
      return { type: "update", op: "--", argument: this.parseUnary(), prefix: true };
    }
    return this.parsePostfix();
  }

  parsePostfix() {
    let node = this.parsePrimary();
    for (;;) {
      if (this.match(".")) {
        node = { type: "member", object: node, property: this.consume().value };
        continue;
      }
      if (this.match("(")) {
        const args = [];
        if (!this.match(")")) {
          do {
            args.push(this.parseExpression());
          } while (this.match(","));
          this.consume(")");
        }
        node = { type: "call", callee: node, args };
        continue;
      }
      if (this.match("++")) {
        node = { type: "update", op: "++", argument: node, prefix: false };
        continue;
      }
      if (this.match("--")) {
        node = { type: "update", op: "--", argument: node, prefix: false };
        continue;
      }
      break;
    }
    return node;
  }

  parsePrimary() {
    const token = this.consume();
    if (token.type === "number") {
      return { type: "literal", value: token.value };
    }
    if (token.value === "true" || token.value === "false") {
      return { type: "literal", value: token.value === "true" };
    }
    if (token.value === "(") {
      const expression = this.parseExpression();
      this.consume(")");
      return expression;
    }
    if (token.type === "identifier") {
      return { type: "identifier", name: token.value };
    }
    throw new Error(`Unexpected GLSL token: ${token.value}`);
  }
}

function defaultValueForType(type) {
  if (type === "bool") {
    return false;
  }
  if (type === "vec2") {
    return vec2(0);
  }
  if (type === "vec3") {
    return vec3(0);
  }
  if (type === "vec4") {
    return vec4(0);
  }
  return 0;
}

class ReturnValue extends Error {
  constructor(value) {
    super("return");
    this.value = value;
  }
}

class Scope {
  constructor(parent = null) {
    this.parent = parent;
    this.values = new Map();
  }

  has(name) {
    return this.values.has(name) || Boolean(this.parent?.has(name));
  }

  get(name) {
    if (this.values.has(name)) {
      return this.values.get(name);
    }
    if (this.parent) {
      return this.parent.get(name);
    }
    throw new Error(`Unknown GLSL identifier: ${name}`);
  }

  set(name, value) {
    if (this.values.has(name)) {
      this.values.set(name, cloneValue(value));
      return;
    }
    if (this.parent?.has(name)) {
      this.parent.set(name, value);
      return;
    }
    this.values.set(name, cloneValue(value));
  }

  define(name, value) {
    this.values.set(name, cloneValue(value));
  }
}

function cloneValue(value) {
  return isVector(value) ? [...value] : value;
}

function castValue(value, type) {
  if (type === "int") {
    return Math.trunc(finiteNumber(value));
  }
  if (type === "float") {
    return finiteNumber(value);
  }
  if (type === "bool") {
    return truthy(value);
  }
  if (type === "vec2") {
    return vec2(value);
  }
  if (type === "vec3") {
    return vec3(value);
  }
  if (type === "vec4") {
    return vec4(value);
  }
  return value;
}

function binaryValue(op, left, right) {
  switch (op) {
    case "+": return add(left, right);
    case "-": return sub(left, right);
    case "*": return mul(left, right);
    case "/": return div(left, right);
    case "<": return left < right;
    case ">": return left > right;
    case "<=": return left <= right;
    case ">=": return left >= right;
    case "==": return left === right;
    case "!=": return left !== right;
    case "&&": return truthy(left) && truthy(right);
    case "||": return truthy(left) || truthy(right);
    default:
      throw new Error(`Unsupported GLSL operator: ${op}`);
  }
}

function evalLValue(node, scope, runtime) {
  if (node.type === "identifier") {
    return {
      get: () => scope.get(node.name),
      set: (value) => {
        scope.set(node.name, value);
        return value;
      }
    };
  }
  if (node.type === "member") {
    const objectLValue = evalLValue(node.object, scope, runtime);
    return {
      get: () => getSwizzle(objectLValue.get(), node.property),
      set: (value) => {
        const target = objectLValue.get();
        setSwizzle(target, node.property, value);
        objectLValue.set(target);
        return value;
      }
    };
  }
  throw new Error("Unsupported GLSL assignment target");
}

function evalExpression(node, scope, runtime) {
  switch (node.type) {
    case "literal":
      return cloneValue(node.value);
    case "identifier":
      return scope.get(node.name);
    case "member":
      return getSwizzle(evalExpression(node.object, scope, runtime), node.property);
    case "unary": {
      const value = evalExpression(node.argument, scope, runtime);
      if (node.op === "-") {
        return neg(value);
      }
      if (node.op === "!") {
        return !truthy(value);
      }
      return value;
    }
    case "update": {
      const lvalue = evalLValue(node.argument, scope, runtime);
      const current = lvalue.get();
      const next = node.op === "++" ? add(current, 1) : sub(current, 1);
      lvalue.set(next);
      return node.prefix ? next : current;
    }
    case "binary":
      if (node.op === "&&") {
        return truthy(evalExpression(node.left, scope, runtime)) && truthy(evalExpression(node.right, scope, runtime));
      }
      if (node.op === "||") {
        return truthy(evalExpression(node.left, scope, runtime)) || truthy(evalExpression(node.right, scope, runtime));
      }
      return binaryValue(node.op, evalExpression(node.left, scope, runtime), evalExpression(node.right, scope, runtime));
    case "ternary":
      return truthy(evalExpression(node.condition, scope, runtime))
        ? evalExpression(node.consequent, scope, runtime)
        : evalExpression(node.alternate, scope, runtime);
    case "assign": {
      const lvalue = evalLValue(node.left, scope, runtime);
      const right = evalExpression(node.right, scope, runtime);
      const current = lvalue.get();
      const value = node.op === "="
        ? right
        : node.op === "+="
          ? add(current, right)
          : node.op === "-="
            ? sub(current, right)
            : node.op === "*="
              ? mul(current, right)
              : div(current, right);
      return lvalue.set(value);
    }
    case "call": {
      const callee = node.callee.type === "identifier" ? node.callee.name : "";
      const args = node.args.map((arg) => evalExpression(arg, scope, runtime));
      if (BUILTINS[callee]) {
        return BUILTINS[callee](...args);
      }
      return runtime.call(callee, args);
    }
    default:
      throw new Error(`Unsupported GLSL expression node: ${node.type}`);
  }
}

function executeStatement(statement, scope, runtime) {
  switch (statement.type) {
    case "empty":
      return;
    case "block":
      for (const child of statement.body) {
        executeStatement(child, scope, runtime);
      }
      return;
    case "var":
      scope.define(statement.name, castValue(evalExpression(statement.init, scope, runtime), statement.varType));
      return;
    case "expr":
      evalExpression(statement.expression, scope, runtime);
      return;
    case "return":
      throw new ReturnValue(evalExpression(statement.expression, scope, runtime));
    case "if":
      if (truthy(evalExpression(statement.condition, scope, runtime))) {
        executeStatement(statement.consequent, scope, runtime);
      } else if (statement.alternate) {
        executeStatement(statement.alternate, scope, runtime);
      }
      return;
    case "for": {
      executeStatement(statement.init, scope, runtime);
      for (let guard = 0; guard < 10000; guard += 1) {
        if (statement.condition && !truthy(evalExpression(statement.condition, scope, runtime))) {
          return;
        }
        executeStatement(statement.body, scope, runtime);
        if (statement.update) {
          evalExpression(statement.update, scope, runtime);
        }
      }
      throw new Error("GLSL for-loop exceeded exporter safety limit");
    }
    default:
      throw new Error(`Unsupported GLSL statement node: ${statement.type}`);
  }
}

function normalizedDistanceSource(source) {
  const text = String(source || "").trim();
  if (!text) {
    throw new Error("Implicit CAD model has no GLSL source");
  }
  return `${text}

float implicit_distance(vec3 p) {
  return sdf(p);
}
`;
}

function normalizedColorSource(source) {
  const text = String(source || "").trim();
  if (!text) {
    throw new Error("Implicit CAD model has no GLSL source");
  }
  const hasColorFunction = /\bvec3\s+color\s*\(/.test(text);
  return `${text}

vec3 implicit_color(vec3 p, vec3 normal) {
  ${hasColorFunction ? "return color(p, normal);" : "return vec3(0.831372549, 0.831372549, 0.847058824);"}
}
`;
}

function createImplicitCadProgramRuntime(model, source, functionName) {
  const program = new Parser(tokenize(source)).parseProgram();
  if (!program.functions.has(functionName)) {
    throw new Error(`Implicit CAD GLSL source did not define ${functionName}`);
  }
  const globals = new Scope();
  for (const [name, value] of Object.entries({
    PI: Math.PI,
    TWO_PI: Math.PI * 2,
  })) {
    globals.define(name, value);
  }
  for (const [name, uniform] of Object.entries(model?.uniforms || {})) {
    globals.define(name, castValue(uniform?.value, uniform?.type));
  }
  const runtime = {
    call(name, args) {
      const fn = program.functions.get(name);
      if (!fn) {
        throw new Error(`Unknown GLSL function: ${name}`);
      }
      const scope = new Scope(globals);
      fn.params.forEach((param, index) => {
        scope.define(param.name, castValue(args[index], param.type));
      });
      try {
        executeStatement(fn.body, scope, runtime);
      } catch (error) {
        if (error instanceof ReturnValue) {
          return castValue(error.value, fn.returnType);
        }
        throw error;
      }
      return defaultValueForType(fn.returnType);
    }
  };
  for (const global of program.globals) {
    executeStatement(global, globals, runtime);
  }
  return runtime;
}

export function createImplicitCadSdfEvaluator(model) {
  const source = normalizedDistanceSource(model?.glslSource || model?.distanceSource);
  const runtime = createImplicitCadProgramRuntime(model, source, "implicit_distance");
  return (x, y, z) => finiteNumber(runtime.call("implicit_distance", [vec3(x, y, z)]), 1e6);
}

export function createImplicitCadColorEvaluator(model) {
  const source = normalizedColorSource(model?.colorSource || model?.glslSource || model?.distanceSource);
  const runtime = createImplicitCadProgramRuntime(model, source, "implicit_color");
  return (point, normal = [0, 0, 1]) => {
    const value = runtime.call("implicit_color", [vec3(point), vec3(normal)]);
    return vec3(value).map((component) => Math.min(Math.max(finiteNumber(component, 0), 0), 1));
  };
}

export const implicitSdfEvaluatorInternals = {
  BUILTINS,
  tokenize,
  Parser,
};
