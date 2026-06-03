import { IMPLICIT_CAD_SCHEMA } from "../packages/implicitjs/src/lib/implicitCad/schema.js";

export const SCHEMA = IMPLICIT_CAD_SCHEMA;
export const PI = Math.PI;
export const TWO_PI = Math.PI * 2;
export const SQRT2 = Math.sqrt(2);
export const SQRT3 = Math.sqrt(3);

function numberLiteral(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    throw new Error(`Expected finite number, got ${value}`);
  }
  if (Object.is(numeric, -0)) {
    return "0.0";
  }
  return Number.isInteger(numeric) ? `${numeric}.0` : String(numeric);
}

function componentList(value, dimension) {
  if (typeof value === "number") {
    return Array.from({ length: dimension }, () => numberLiteral(value));
  }
  if (!Array.isArray(value) && !ArrayBuffer.isView(value)) {
    throw new Error(`Expected vec${dimension} array or scalar`);
  }
  return Array.from({ length: dimension }, (_, index) => numberLiteral(value[index] ?? 0));
}

export function vec2(value, y = null) {
  const components = y === null ? componentList(value, 2) : [numberLiteral(value), numberLiteral(y)];
  return `vec2(${components.join(", ")})`;
}

export function vec3(value, y = null, z = null) {
  const components = y === null && z === null
    ? componentList(value, 3)
    : [numberLiteral(value), numberLiteral(y), numberLiteral(z)];
  return `vec3(${components.join(", ")})`;
}

export function expr(value) {
  if (value && typeof value === "object" && typeof value.expr === "string") {
    return value.expr;
  }
  if (typeof value === "number") {
    return numberLiteral(value);
  }
  return String(value);
}

export function glsl(strings, ...values) {
  return strings.reduce((result, part, index) => (
    `${result}${part}${index < values.length ? expr(values[index]) : ""}`
  ), "");
}

function reduceCall(values, callName, radius = null) {
  const parts = values.map(expr);
  if (parts.length === 0) {
    throw new Error(`${callName} requires at least one field`);
  }
  if (parts.length === 1) {
    return parts[0];
  }
  return parts.slice(1).reduce((acc, value) => (
    radius === null
      ? `${callName}(${acc}, ${value})`
      : `${callName}(${acc}, ${value}, ${numberLiteral(radius)})`
  ), parts[0]);
}

function reduceCallWithArgs(values, callName, args = []) {
  const parts = values.map(expr);
  if (parts.length === 0) {
    throw new Error(`${callName} requires at least one field`);
  }
  if (parts.length === 1) {
    return parts[0];
  }
  const suffix = args.length > 0 ? `, ${args.map(expr).join(", ")}` : "";
  return parts.slice(1).reduce((acc, value) => `${callName}(${acc}, ${value}${suffix})`, parts[0]);
}

export function linearMap(value, inMin, inMax, outMin, outMax) {
  return `implicit_linear_map(${expr(value)}, ${numberLiteral(inMin)}, ${numberLiteral(inMax)}, ${numberLiteral(outMin)}, ${numberLiteral(outMax)})`;
}

export function ramp(value, inMin, inMax, outMin, outMax) {
  return `implicit_ramp(${expr(value)}, ${numberLiteral(inMin)}, ${numberLiteral(inMax)}, ${numberLiteral(outMin)}, ${numberLiteral(outMax)})`;
}

export function twoBodyField(a, b) {
  return `implicit_two_body_field(${expr(a)}, ${expr(b)})`;
}

export function twoBodyPolar(a, b, angle) {
  return `implicit_two_body_polar(${expr(a)}, ${expr(b)}, ${numberLiteral(angle)})`;
}

export function triangleWaveEven(value, period) {
  return `implicit_triangle_wave_even(${expr(value)}, ${expr(period)})`;
}

export function triangleWaveEvenPositive(value, period) {
  return `implicit_triangle_wave_even_positive(${expr(value)}, ${expr(period)})`;
}

export function triangleWaveOdd(value, period) {
  return `implicit_triangle_wave_odd(${expr(value)}, ${expr(period)})`;
}

export function triangleWaveOddPositive(value, period) {
  return `implicit_triangle_wave_odd_positive(${expr(value)}, ${expr(period)})`;
}

export function unionSharp(values) {
  return reduceCall(values, "implicit_union_sharp");
}

export function intersectSharp(values) {
  return reduceCall(values, "implicit_intersect_sharp");
}

export function unionRound(values, radius = 0) {
  return reduceCall(values, "implicit_union_round", radius);
}

export function intersectRound(values, radius = 0) {
  return reduceCall(values, "implicit_intersect_round", radius);
}

export function unionChamfer(values, radius = 0) {
  return reduceCall(values, "implicit_union_chamfer", radius);
}

export function intersectChamfer(values, radius = 0) {
  return reduceCall(values, "implicit_intersect_chamfer", radius);
}

export function unionExp(values, radius = 0) {
  return reduceCall(values, "implicit_union_exp", radius);
}

export function intersectExp(values, radius = 0) {
  return reduceCall(values, "implicit_intersect_exp", radius);
}

export function unionLpNorm(values, radius = 0, normPower = 2) {
  return reduceCallWithArgs(values, "implicit_union_lp_norm", [numberLiteral(radius), numberLiteral(normPower)]);
}

export function intersectLpNorm(values, radius = 0, normPower = 2) {
  return reduceCallWithArgs(values, "implicit_intersect_lp_norm", [numberLiteral(radius), numberLiteral(normPower)]);
}

export function unionRvachev(values, radius = 0) {
  return reduceCall(values, "implicit_union_rvachev", radius);
}

export function intersectRvachev(values, radius = 0) {
  return reduceCall(values, "implicit_intersect_rvachev", radius);
}

export function booleanSharp() {
  return { union: unionSharp, intersect: intersectSharp };
}

export function booleanRound(radius = 0) {
  return {
    radius,
    union: (values) => unionRound(values, radius),
    intersect: (values) => intersectRound(values, radius),
  };
}

export function booleanExp(radius = 0) {
  return {
    radius,
    union: (values) => unionExp(values, radius),
    intersect: (values) => intersectExp(values, radius),
  };
}

export function booleanLp(normPower, radius = 0) {
  return {
    radius,
    normPower,
    union: (values) => unionLpNorm(values, radius, normPower),
    intersect: (values) => intersectLpNorm(values, radius, normPower),
  };
}

export function booleanRvachev(radius = 0) {
  return {
    radius,
    union: (values) => unionRvachev(values, radius),
    intersect: (values) => intersectRvachev(values, radius),
  };
}

export function booleanChamfer(radius = 0) {
  return {
    radius,
    union: (values) => unionChamfer(values, radius),
    intersect: (values) => intersectChamfer(values, radius),
  };
}

export function difference(target, tools, {
  union = unionSharp,
  intersect = intersectSharp
} = {}) {
  const toolList = Array.isArray(tools) ? tools : [tools];
  const toolUnion = union(toolList);
  return intersect([target, `-(${toolUnion})`]);
}

export function sphere(p, center, radius) {
  return `implicit_sphere(${expr(p)}, ${vec3(center)}, ${numberLiteral(radius)})`;
}

export function circle(p, center, radius) {
  return sphere(p, center, radius);
}

export function boxCentered(p, size, { center = [0, 0, 0] } = {}) {
  return `implicit_box_centered(${expr(p)}, ${vec3(size)}, ${vec3(center)})`;
}

export function plane(p, origin, normal) {
  return `implicit_plane(${expr(p)}, ${vec3(origin)}, ${vec3(normal)})`;
}

export function lineSegment(p, endpointA, endpointB) {
  return `implicit_line_segment(${expr(p)}, ${vec3(endpointA)}, ${vec3(endpointB)})`;
}

export function torus(p, majorRadius, minorRadius) {
  return `implicit_torus(${expr(p)}, ${numberLiteral(majorRadius)}, ${numberLiteral(minorRadius)})`;
}

export function axis(p, origin, direction) {
  return `implicit_axis(${expr(p)}, ${vec3(origin)}, ${vec3(direction)})`;
}

export function cylinder(p, origin, direction, radius) {
  return `implicit_cylinder(${expr(p)}, ${vec3(origin)}, ${vec3(direction)}, ${numberLiteral(radius)})`;
}

export function cylinderCapped(p, endpointA, endpointB, radius) {
  return `implicit_cylinder_capped(${expr(p)}, ${vec3(endpointA)}, ${vec3(endpointB)}, ${numberLiteral(radius)})`;
}

export function capsule(p, endpointA, endpointB, radius) {
  return `implicit_capsule(${expr(p)}, ${vec3(endpointA)}, ${vec3(endpointB)}, ${numberLiteral(radius)})`;
}

export function coneCapsule(p, endpointA, endpointB, radiusA, radiusB) {
  return `implicit_cone_capsule(${expr(p)}, ${vec3(endpointA)}, ${vec3(endpointB)}, ${numberLiteral(radiusA)}, ${numberLiteral(radiusB)})`;
}

export function cone(p, apex, direction, halfAngle) {
  return `implicit_cone(${expr(p)}, ${vec3(apex)}, ${vec3(direction)}, ${numberLiteral(halfAngle)})`;
}

export function coneCapped(p, endpointA, endpointB, radiusA, radiusB) {
  return `implicit_cone_capped(${expr(p)}, ${vec3(endpointA)}, ${vec3(endpointB)}, ${numberLiteral(radiusA)}, ${numberLiteral(radiusB)})`;
}

export function shell(distance, thickness, bias = 0) {
  return `implicit_shell(${expr(distance)}, ${numberLiteral(thickness)}, ${numberLiteral(bias)})`;
}

export function rotateAxis(p, origin, direction, angle) {
  return `implicit_rotate_axis(${expr(p)}, ${vec3(origin)}, ${vec3(direction)}, ${numberLiteral(angle)})`;
}

export function repeatCentered(p, period) {
  return `implicit_repeat_centered(${expr(p)}, ${vec3(period)})`;
}

export function remapCylindrical(p, circumference) {
  return `implicit_remap_cylindrical(${expr(p)}, ${numberLiteral(circumference)})`;
}

export function cubicGrid(p, size) {
  return `implicit_cubic_grid(${expr(p)}, ${vec3(size)})`;
}

export function squareHoneycomb(p, size) {
  return `implicit_square_honeycomb(${expr(p)}, ${vec2(size)})`;
}

export function squareHoneycombReinforced(p, size, { rotation = 0.25, rotation2 = null } = {}) {
  return `implicit_square_honeycomb_reinforced(${expr(p)}, ${vec2(size)}, ${numberLiteral(rotation)}, ${numberLiteral(rotation2 ?? 0)}, ${numberLiteral(rotation2 === null ? 0 : 1)})`;
}

export function squareDiagonalHoneycomb(p, size) {
  return `implicit_square_diagonal_honeycomb(${expr(p)}, ${vec2(size)})`;
}

export function octetHoneycomb(p, size) {
  return `implicit_octet_honeycomb(${expr(p)}, ${vec2(size)})`;
}

export function hexagonalHoneycomb(p, size, { setback = 1 / 3 } = {}) {
  const resolvedSize = typeof size === "number" ? [size, size * SQRT3] : size;
  return `implicit_hexagonal_honeycomb(${expr(p)}, ${vec2(resolvedSize)}, ${numberLiteral(setback)})`;
}

export function triangularHoneycomb(p, size) {
  const resolvedSize = typeof size === "number" ? [size, size * SQRT3] : size;
  return `implicit_triangular_honeycomb(${expr(p)}, ${vec2(resolvedSize)})`;
}

export function tpmsGyroid(p, period, drop = [1, 1, 1]) {
  return `implicit_tpms_gyroid(${expr(p)}, ${vec3(period)}, ${vec3(drop)})`;
}

export function tpmsSchwarz(p, period, { drop = [1, 1, 1], gyroidBlend = 0 } = {}) {
  return `implicit_tpms_schwarz(${expr(p)}, ${vec3(period)}, ${vec3(drop)}, ${numberLiteral(gyroidBlend)})`;
}

export function tpmsDiamond(p, period, { drop = [1, 1, 1], gyroidBlend = 0 } = {}) {
  return `implicit_tpms_diamond(${expr(p)}, ${vec3(period)}, ${vec3(drop)}, ${numberLiteral(gyroidBlend)})`;
}

export function tpmsLidinoid(p, period, { drop = [1, 1, 1], gyroidBlend = 0 } = {}) {
  return `implicit_tpms_lidinoid(${expr(p)}, ${vec3(period)}, ${vec3(drop)}, ${numberLiteral(gyroidBlend)})`;
}

export function tpmsNeovius(p, period, { drop = [1, 1, 1], schwarzBlend = 0 } = {}) {
  return `implicit_tpms_neovius(${expr(p)}, ${vec3(period)}, ${vec3(drop)}, ${numberLiteral(schwarzBlend)})`;
}

export function tpmsSplitP(p, period, { lidinoidBlend = 1, gyroidOctave = 1, schwarzOctave = 1 } = {}) {
  return `implicit_tpms_split_p(${expr(p)}, ${vec3(period)}, ${numberLiteral(lidinoidBlend)}, ${numberLiteral(gyroidOctave)}, ${numberLiteral(schwarzOctave)})`;
}

export function tpmsIwp(p, period, drop = [1, 1, 1]) {
  return `implicit_tpms_iwp(${expr(p)}, ${vec3(period)}, ${vec3(drop)})`;
}

export function distanceFunction(distanceExpression, { point = "p" } = {}) {
  return `float sdf(vec3 ${point}) {\n  return ${expr(distanceExpression)};\n}`;
}

export function colorFunction(colorExpression, { point = "p", normal = "normal" } = {}) {
  return `vec3 color(vec3 ${point}, vec3 ${normal}) {\n  return clamp(${expr(colorExpression)}, vec3(0.0), vec3(1.0));\n}`;
}

function distanceSource(value) {
  return typeof value === "function" || /\bsdf\s*\(/.test(expr(value))
    ? value
    : distanceFunction(value);
}

function colorSource(value) {
  return typeof value === "function" || /\bcolor\s*\(/.test(expr(value))
    ? value
    : colorFunction(value);
}

export function createImplicitModel({
  name = "Implicit CAD",
  description = "",
  units = "mm",
  bounds,
  params = {},
  values = {},
  animations = {},
  render = {},
  glsl = "",
  distance,
  color = "",
} = {}) {
  const glslSource = glsl || [
    distance !== undefined ? distanceSource(distance) : "",
    color ? colorSource(color) : "",
  ].filter(Boolean).join("\n\n");
  return {
    schema: SCHEMA,
    name,
    description,
    units,
    ...(bounds !== undefined ? { bounds } : {}),
    ...(params && Object.keys(params).length ? { params } : {}),
    ...(values && Object.keys(values).length ? { values } : {}),
    ...(animations && Object.keys(animations).length ? { animations } : {}),
    ...(render && Object.keys(render).length ? { render } : {}),
    glsl: glslSource,
  };
}
