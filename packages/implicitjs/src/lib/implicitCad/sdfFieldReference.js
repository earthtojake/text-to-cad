// A SECOND, INDEPENDENT evaluation of a model's signed-distance field -- the oracle the
// field-agreement gate (`sdfField.test.js`) measures `sdfEvaluator.js` against.
//
// Why a second evaluator exists at all
// -----------------------------------
// An implicit model is authored once, in GLSL, and then evaluated TWICE by different code:
//
//   GPU  raymarch : `IMPLICIT_CAD_GLSL_LIBRARY` (GLSL bodies in render.js)
//                   + `normalizeImplicitCadGlslFloatLiterals(model.glslSource)`
//   CPU  meshing  : `sdfEvaluator.js`'s BUILTINS table (the same ~60 helpers, hand-written a
//                   second time in JS) + the RAW, un-normalized `model.glslSource`
//
// Neither input nor implementation is shared, and the CPU side is no longer an export-only
// convenience -- it is the geometry users actually see.
// So this module evaluates the GPU side's inputs -- the shader's own GLSL helper bodies, over
// the shader's own normalized source -- and the test asserts the two agree numerically.
//
// What makes it an oracle rather than a copy
// ------------------------------------------
// It shares the lexer and the parser with `sdfEvaluator.js` (grammar is not the thing under
// test; arithmetic is) and NOTHING else. Every builtin below is written from the GLSL ES spec,
// not ported from the BUILTINS table, and every `implicit_*` helper is resolved to its GLSL
// body from the shader library -- deliberately NOT to the JS table -- which is what lets the
// comparison see a divergence between the two hand-written libraries.
//
// Stated limits (these are the GPU tier's job, not this module's)
// --------------------------------------------------------------
//   * float64, not the shader's `highp` float32. Compare with a tolerance.
//   * `int` is a JS number, so GLSL's truncating integer division is NOT modelled. (Neither
//     does `sdfEvaluator.js`, so this is a blind spot the two share, not a divergence between
//     them.)
//   * No preprocessor, matrices, arrays, or structs. No model GLSL in `models/implicits/`
//     uses any of them, and an attempt to would throw here rather than pass quietly.
//
// It also defines NO globals of its own: `sdfEvaluator.js` predefines `PI`/`TWO_PI`, which
// the shader does not, so a model leaning on them fails here loudly -- correctly, because it
// would fail to compile on the GPU.

import {
  IMPLICIT_CAD_GLSL_LIBRARY,
  normalizeImplicitCadGlslFloatLiterals
} from "./render.js";
import { implicitSdfEvaluatorInternals } from "./sdfEvaluator.js";

const { tokenize, Parser } = implicitSdfEvaluatorInternals;

const TYPE_KEYWORDS = new Set(["float", "int", "bool", "vec2", "vec3", "vec4"]);
const QUALIFIERS = new Set(["const", "highp", "mediump", "lowp", "in", "out", "uniform", "varying"]);

/* -------------------------------------------------------------------------- values --- */

const isVec = Array.isArray;

function num(value) {
  return typeof value === "boolean" ? (value ? 1 : 0) : Number(value);
}

function map1(a, fn) {
  return isVec(a) ? a.map((component) => fn(num(component))) : fn(num(a));
}

function map2(a, b, fn) {
  if (isVec(a) && isVec(b)) {
    return a.map((component, index) => fn(num(component), num(b[index])));
  }
  if (isVec(a)) {
    return a.map((component) => fn(num(component), num(b)));
  }
  if (isVec(b)) {
    return b.map((component) => fn(num(a), num(component)));
  }
  return fn(num(a), num(b));
}

function map3(a, b, c, fn) {
  const size = [a, b, c].reduce((width, value) => (isVec(value) ? Math.max(width, value.length) : width), 0);
  if (!size) {
    return fn(num(a), num(b), num(c));
  }
  const at = (value, index) => (isVec(value) ? num(value[index]) : num(value));
  return Array.from({ length: size }, (_, index) => fn(at(a, index), at(b, index), at(c, index)));
}

/** GLSL constructor rules: flatten the arguments, splat a lone scalar, else take the first N. */
function construct(size, args) {
  const flat = [];
  for (const arg of args) {
    if (isVec(arg)) {
      flat.push(...arg.map(num));
    } else {
      flat.push(num(arg));
    }
  }
  if (flat.length === 0) {
    return Array.from({ length: size }, () => 0);
  }
  if (flat.length === 1) {
    return Array.from({ length: size }, () => flat[0]);
  }
  if (flat.length < size) {
    throw new Error(`GLSL vec${size} constructor given ${flat.length} components`);
  }
  return flat.slice(0, size);
}

function vectorLength(value) {
  if (!isVec(value)) {
    return Math.abs(num(value));
  }
  return Math.sqrt(value.reduce((sum, component) => sum + num(component) * num(component), 0));
}

function dotProduct(a, b) {
  const va = isVec(a) ? a : [a];
  const vb = isVec(b) ? b : [b];
  let sum = 0;
  for (let index = 0; index < va.length; index += 1) {
    sum += num(va[index]) * num(vb[index] ?? 0);
  }
  return sum;
}

/* ------------------------------------------------------------------------ builtins --- */
// Written from the OpenGL ES Shading Language spec (§8 Built-in Functions). Deliberately not
// ported from sdfEvaluator.js's table -- a ported copy would agree with it by construction and
// the test would prove nothing.

const REFERENCE_BUILTINS = {
  float: (value) => num(value),
  int: (value) => Math.trunc(num(value)),
  bool: (value) => Boolean(isVec(value) ? value.some((component) => component) : num(value)),
  vec2: (...args) => construct(2, args),
  vec3: (...args) => construct(3, args),
  vec4: (...args) => construct(4, args),

  radians: (a) => map1(a, (x) => (x * Math.PI) / 180),
  degrees: (a) => map1(a, (x) => (x * 180) / Math.PI),
  sin: (a) => map1(a, Math.sin),
  cos: (a) => map1(a, Math.cos),
  tan: (a) => map1(a, Math.tan),
  asin: (a) => map1(a, Math.asin),
  acos: (a) => map1(a, Math.acos),
  atan: (...args) => (args.length >= 2 ? map2(args[0], args[1], Math.atan2) : map1(args[0], Math.atan)),
  sinh: (a) => map1(a, Math.sinh),
  cosh: (a) => map1(a, Math.cosh),
  tanh: (a) => map1(a, Math.tanh),
  asinh: (a) => map1(a, Math.asinh),
  acosh: (a) => map1(a, Math.acosh),
  atanh: (a) => map1(a, Math.atanh),

  pow: (a, b) => map2(a, b, Math.pow),
  exp: (a) => map1(a, Math.exp),
  log: (a) => map1(a, Math.log),
  exp2: (a) => map1(a, (x) => Math.pow(2, x)),
  log2: (a) => map1(a, Math.log2),
  sqrt: (a) => map1(a, Math.sqrt),
  inversesqrt: (a) => map1(a, (x) => 1 / Math.sqrt(x)),

  abs: (a) => map1(a, Math.abs),
  sign: (a) => map1(a, Math.sign),
  floor: (a) => map1(a, Math.floor),
  trunc: (a) => map1(a, Math.trunc),
  round: (a) => map1(a, Math.round),
  roundEven: (a) => map1(a, (x) => {
    const nearest = Math.round(x);
    return Math.abs(x % 1) === 0.5 && nearest % 2 !== 0 ? nearest - Math.sign(x) : nearest;
  }),
  ceil: (a) => map1(a, Math.ceil),
  fract: (a) => map1(a, (x) => x - Math.floor(x)),
  mod: (a, b) => map2(a, b, (x, y) => x - y * Math.floor(x / y)),
  min: (a, b) => map2(a, b, Math.min),
  max: (a, b) => map2(a, b, Math.max),
  clamp: (a, low, high) => map3(a, low, high, (x, lo, hi) => Math.min(Math.max(x, lo), hi)),
  mix: (a, b, t) => map3(a, b, t, (x, y, s) => x * (1 - s) + y * s),
  step: (edge, a) => map2(edge, a, (e, x) => (x < e ? 0 : 1)),
  smoothstep: (edge0, edge1, a) => map3(edge0, edge1, a, (e0, e1, x) => {
    const t = Math.min(Math.max((x - e0) / (e1 - e0), 0), 1);
    return t * t * (3 - 2 * t);
  }),

  length: vectorLength,
  distance: (a, b) => vectorLength(map2(a, b, (x, y) => x - y)),
  dot: dotProduct,
  cross: (a, b) => [
    num(a[1]) * num(b[2]) - num(a[2]) * num(b[1]),
    num(a[2]) * num(b[0]) - num(a[0]) * num(b[2]),
    num(a[0]) * num(b[1]) - num(a[1]) * num(b[0]),
  ],
  // Spec normalize: v / length(v), with NO guard at zero. sdfEvaluator.js guards below 1e-12
  // and returns the zero vector; the GPU returns NaN. Left unguarded on purpose so the gate
  // can see a model that actually reaches it.
  normalize: (a) => {
    const len = vectorLength(a);
    return map1(a, (x) => x / len);
  },
  reflect: (incident, normal) => {
    const scale = 2 * dotProduct(normal, incident);
    return map2(incident, normal, (i, n) => i - scale * n);
  },
  faceforward: (n, incident, reference) => (dotProduct(reference, incident) < 0 ? n : map1(n, (x) => -x)),
};

/* ------------------------------------------------------------------------- parsing --- */

/** GLSL overloads by name. The shipped parser keys functions by name alone, so the library's
 *  float/vec2/vec3 `implicit_triangle_wave_even` triple collapses to whichever came last;
 *  resolving a call needs all of them. */
class OverloadParser extends Parser {
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
        const overloads = functions.get(name) || [];
        overloads.push({ name, params, returnType: type, body: this.parseBlock() });
        functions.set(name, overloads);
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
}

function widthOfType(type) {
  return type === "vec2" ? 2 : type === "vec3" ? 3 : type === "vec4" ? 4 : 1;
}

function argumentMatchesParam(value, type) {
  const width = widthOfType(type);
  return width === 1 ? !isVec(value) : isVec(value) && value.length === width;
}

function resolveOverload(overloads, args, name) {
  const sameArity = overloads.filter((candidate) => candidate.params.length === args.length);
  if (!sameArity.length) {
    throw new Error(`No ${name} overload takes ${args.length} arguments`);
  }
  const exact = sameArity.find((candidate) => candidate.params.every(
    (param, index) => argumentMatchesParam(args[index], param.type)
  ));
  return exact || sameArity[0];
}

/* --------------------------------------------------------------------- evaluation --- */

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

  assign(name, value) {
    if (this.values.has(name)) {
      this.values.set(name, copy(value));
      return;
    }
    if (this.parent?.has(name)) {
      this.parent.assign(name, value);
      return;
    }
    this.values.set(name, copy(value));
  }

  declare(name, value) {
    this.values.set(name, copy(value));
  }
}

function copy(value) {
  return isVec(value) ? [...value] : value;
}

function castTo(type, value) {
  switch (type) {
    case "int": return Math.trunc(num(value));
    case "float": return num(value);
    case "bool": return Boolean(isVec(value) ? value.some((component) => component) : num(value));
    case "vec2": return construct(2, [value]);
    case "vec3": return construct(3, [value]);
    case "vec4": return construct(4, [value]);
    default: return value;
  }
}

function defaultOfType(type) {
  return type === "bool" ? false : widthOfType(type) === 1 ? 0 : Array.from({ length: widthOfType(type) }, () => 0);
}

const SWIZZLE_INDEX = { x: 0, y: 1, z: 2, w: 3, r: 0, g: 1, b: 2, a: 3, s: 0, t: 1, p: 2, q: 3 };

function swizzle(value, property) {
  const indices = String(property).split("").map((component) => SWIZZLE_INDEX[component]);
  if (!indices.length || indices.some((index) => index === undefined)) {
    throw new Error(`Unsupported GLSL member access: .${property}`);
  }
  const source = isVec(value) ? value : [value];
  const picked = indices.map((index) => {
    if (index >= source.length) {
      throw new Error(`GLSL swizzle .${property} out of range for a ${source.length}-component value`);
    }
    return num(source[index]);
  });
  return picked.length === 1 ? picked[0] : picked;
}

function truthy(value) {
  return isVec(value) ? value.some((component) => truthy(component)) : Boolean(value);
}

class ReturnSignal {
  constructor(value) {
    this.value = value;
  }
}
const BREAK = Symbol("break");
const CONTINUE = Symbol("continue");

const LOOP_GUARD = 100000;

function createInterpreter(functions, globalScope) {
  function callFunction(name, args) {
    const overloads = functions.get(name);
    if (!overloads) {
      throw new Error(`Unknown GLSL function: ${name}`);
    }
    const fn = resolveOverload(overloads, args, name);
    const scope = new Scope(globalScope);
    fn.params.forEach((param, index) => {
      scope.declare(param.name, castTo(param.type, args[index]));
    });
    const outcome = run(fn.body, scope);
    return outcome instanceof ReturnSignal ? castTo(fn.returnType, outcome.value) : defaultOfType(fn.returnType);
  }

  function lvalue(node, scope) {
    if (node.type === "identifier") {
      return {
        read: () => scope.get(node.name),
        write: (value) => {
          scope.assign(node.name, value);
          return value;
        },
      };
    }
    if (node.type === "member") {
      const object = lvalue(node.object, scope);
      return {
        read: () => swizzle(object.read(), node.property),
        write: (value) => {
          const target = copy(object.read());
          if (!isVec(target)) {
            throw new Error(`Cannot assign .${node.property} on a scalar`);
          }
          const indices = String(node.property).split("").map((component) => SWIZZLE_INDEX[component]);
          const source = isVec(value) ? value : [value];
          indices.forEach((targetIndex, index) => {
            if (targetIndex === undefined) {
              throw new Error(`Unsupported GLSL member assignment: .${node.property}`);
            }
            target[targetIndex] = num(source[index] ?? source[0]);
          });
          object.write(target);
          return value;
        },
      };
    }
    throw new Error("Unsupported GLSL assignment target");
  }

  function evaluate(node, scope) {
    switch (node.type) {
      case "literal":
        return copy(node.value);
      case "identifier":
        return scope.get(node.name);
      case "member":
        return swizzle(evaluate(node.object, scope), node.property);
      case "unary": {
        const value = evaluate(node.argument, scope);
        return node.op === "-" ? map1(value, (x) => -x) : node.op === "!" ? !truthy(value) : value;
      }
      case "update": {
        const target = lvalue(node.argument, scope);
        const current = target.read();
        const next = map2(current, 1, node.op === "++" ? (x, y) => x + y : (x, y) => x - y);
        target.write(next);
        return node.prefix ? next : current;
      }
      case "binary": {
        if (node.op === "&&") {
          return truthy(evaluate(node.left, scope)) && truthy(evaluate(node.right, scope));
        }
        if (node.op === "||") {
          return truthy(evaluate(node.left, scope)) || truthy(evaluate(node.right, scope));
        }
        const left = evaluate(node.left, scope);
        const right = evaluate(node.right, scope);
        switch (node.op) {
          case "+": return map2(left, right, (x, y) => x + y);
          case "-": return map2(left, right, (x, y) => x - y);
          case "*": return map2(left, right, (x, y) => x * y);
          case "/": return map2(left, right, (x, y) => x / y);
          case "<": return num(left) < num(right);
          case ">": return num(left) > num(right);
          case "<=": return num(left) <= num(right);
          case ">=": return num(left) >= num(right);
          case "==": return isVec(left) || isVec(right)
            ? String(left) === String(right)
            : num(left) === num(right);
          case "!=": return isVec(left) || isVec(right)
            ? String(left) !== String(right)
            : num(left) !== num(right);
          default:
            throw new Error(`Unsupported GLSL operator: ${node.op}`);
        }
      }
      case "ternary":
        return truthy(evaluate(node.condition, scope))
          ? evaluate(node.consequent, scope)
          : evaluate(node.alternate, scope);
      case "assign": {
        const target = lvalue(node.left, scope);
        const right = evaluate(node.right, scope);
        if (node.op === "=") {
          return target.write(right);
        }
        const current = target.read();
        const combine = node.op === "+=" ? (x, y) => x + y
          : node.op === "-=" ? (x, y) => x - y
            : node.op === "*=" ? (x, y) => x * y
              : (x, y) => x / y;
        return target.write(map2(current, right, combine));
      }
      case "call": {
        const callee = node.callee.type === "identifier" ? node.callee.name : "";
        const args = node.args.map((arg) => evaluate(arg, scope));
        // Program functions win over builtins: the shader library's `implicit_*` bodies are
        // exactly what this oracle exists to evaluate.
        if (functions.has(callee)) {
          return callFunction(callee, args);
        }
        if (REFERENCE_BUILTINS[callee]) {
          return REFERENCE_BUILTINS[callee](...args);
        }
        throw new Error(`Unknown GLSL function: ${callee}`);
      }
      default:
        throw new Error(`Unsupported GLSL expression node: ${node.type}`);
    }
  }

  /** Returns undefined, BREAK, CONTINUE, or a ReturnSignal. */
  function run(statement, scope) {
    switch (statement.type) {
      case "empty":
        return undefined;
      case "block": {
        const inner = new Scope(scope);
        for (const child of statement.body) {
          const outcome = run(child, inner);
          if (outcome !== undefined) {
            return outcome;
          }
        }
        return undefined;
      }
      case "var":
        scope.declare(statement.name, castTo(statement.varType, evaluate(statement.init, scope)));
        return undefined;
      case "expr":
        evaluate(statement.expression, scope);
        return undefined;
      case "return":
        return new ReturnSignal(evaluate(statement.expression, scope));
      case "break":
        return BREAK;
      case "continue":
        return CONTINUE;
      case "if":
        if (truthy(evaluate(statement.condition, scope))) {
          return run(statement.consequent, scope);
        }
        return statement.alternate ? run(statement.alternate, scope) : undefined;
      case "for": {
        const header = new Scope(scope);
        run(statement.init, header);
        for (let guard = 0; guard < LOOP_GUARD; guard += 1) {
          if (statement.condition && !truthy(evaluate(statement.condition, header))) {
            return undefined;
          }
          const outcome = run(statement.body, header);
          if (outcome === BREAK) {
            return undefined;
          }
          if (outcome instanceof ReturnSignal) {
            return outcome;
          }
          if (statement.update) {
            evaluate(statement.update, header);
          }
        }
        throw new Error("GLSL for-loop exceeded the reference evaluator's safety limit");
      }
      default:
        throw new Error(`Unsupported GLSL statement node: ${statement.type}`);
    }
  }

  return { callFunction, run, evaluate };
}

/* ------------------------------------------------------------------------ assembly --- */

/** The exact GLSL the GPU compiles for `sdf`: the shader's helper library, then the model's
 *  source AS THE SHADER NORMALIZES IT, then the shader's own `implicit_distance` wrapper. */
export function referenceSdfProgramSource(model) {
  const raw = String(model?.glslSource || model?.distanceSource || "").trim();
  if (!raw) {
    throw new Error("Implicit CAD model has no GLSL source");
  }
  return `${IMPLICIT_CAD_GLSL_LIBRARY}

${normalizeImplicitCadGlslFloatLiterals(raw)}

float implicit_distance(vec3 p) {
  return sdf(p);
}
`;
}

/**
 * An `(x, y, z) -> distance` evaluator built from the shader's inputs rather than the CPU
 * evaluator's. Throws -- never falls back to a default -- when the program cannot be built or
 * a call cannot be resolved.
 */
export function createReferenceSdfEvaluator(model) {
  const program = new OverloadParser(tokenize(referenceSdfProgramSource(model))).parseProgram();
  if (!program.functions.has("sdf")) {
    throw new Error("Implicit CAD GLSL source did not define sdf");
  }
  const globalScope = new Scope();
  for (const [name, uniform] of Object.entries(model?.uniforms || {})) {
    globalScope.declare(name, castTo(uniform?.type, uniform?.value));
  }
  const interpreter = createInterpreter(program.functions, globalScope);
  for (const global of program.globals) {
    interpreter.run(global, globalScope);
  }
  return (x, y, z) => num(interpreter.callFunction("implicit_distance", [[num(x), num(y), num(z)]]));
}

export const sdfFieldReferenceInternals = {
  REFERENCE_BUILTINS,
  OverloadParser,
  createInterpreter,
};
