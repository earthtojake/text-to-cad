/**
 * GLSL -> JS compiler: the fast backend of the implicit SDF evaluator.
 *
 * The interpreter (`sdfEvaluator.js`) walks the parsed AST on EVERY call, and a bake makes
 * ~10^6 calls. This module walks the same AST ONCE and emits an equivalent JS function via
 * `new Function`. Two emission tiers:
 *
 *  - CONSERVATIVE: call the interpreter's own helper/builtin function objects in the
 *    interpreter's order -- bit-identical by construction. This is the fallback for any
 *    expression whose type cannot be established.
 *  - TYPED: GLSL is statically typed, so
 *    when an expression's SHAPE (scalar vs vec width) is certain, arithmetic inlines to raw
 *    JS operators and componentwise array literals. Each inlined form performs the same
 *    per-component IEEE-754 operations `mapBinary`/`mapUnary` would ("?? 0" fills are
 *    no-ops when widths match, which is exactly when we inline), so results stay
 *    bit-identical -- now verified by the harness rather than by construction. Phase 1
 *    measured why this tier exists: dispatch removal alone bought 1.4-3x and the remaining
 *    cost was mapBinary's Array.from closures allocating per op.
 *
 * Shape inference trusts DECLARED types (params, `var` types, uniform types, user-function
 * return types). A model that lies about its types -- declares float, stores a vec -- could
 * make an inlined `+` concatenate instead of add. The corpus differential gate would catch
 * it loudly, and the wider ecosystem already enforces honesty: every model must also
 * compile as a real GLSL ES shader for the raymarcher, which rejects ill-typed programs.
 * Where a shape is unknown or conflicting, emission stays conservative.
 *
 * Semantics deliberately mirrored (plan §2.3): function-scoped declarations (blocks share
 * scope -> all locals hoisted); Scope.set clones vectors (stores route through cloneValue
 * EXCEPT where the stored value is a scalar or provably fresh, where the clone is an
 * identity); `&&`/`||` short-circuit through truthy; `==` is `===` on raw values; the
 * 10,000-iteration for-guard throws the interpreter's exact message; `continue` runs the
 * loop update (it lives in the JS `for` header).
 *
 * Failure policy: `compileImplicitProgramRuntime` returns null on ANY problem and the
 * caller falls back to the interpreter. Worst outcome is slowness, never wrong geometry.
 */

/** Thrown internally for any construct outside the interpreter-verified surface. */
class CompileUnsupported extends Error {}

function unsupported(what) {
  throw new CompileUnsupported(String(what));
}

function nameLiteral(value) {
  return JSON.stringify(String(value));
}

function numberLiteral(value) {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    unsupported(`literal ${String(value)}`);
  }
  // String(n) is the shortest round-trip form; re-parsing yields the identical double.
  return Object.is(value, -0) ? "-0" : String(value);
}

/** GLSL type string -> shape: "s" for scalars, a width for vecs, null for unknown. */
function shapeOfType(type) {
  if (type === "float" || type === "int" || type === "bool") {
    return "s";
  }
  if (type === "vec2") return 2;
  if (type === "vec3") return 3;
  if (type === "vec4") return 4;
  return null;
}

// Builtin result shapes, used only to PROPAGATE types -- the emitted code still calls the
// shared BUILTINS entries. A name absent from all sets simply yields an unknown shape and
// conservative emission downstream. Wrong entries here would inline wrongly and be caught
// by the corpus differential gate, so only well-understood builtins are listed.
const SCALAR_BUILTINS = new Set(["float", "int", "bool", "length", "dot"]);
const CONSTRUCTOR_SHAPES = { vec2: 2, vec3: 3, vec4: 4, cross: 3 };
const SHAPE_PRESERVING = new Set([
  "abs", "sign", "floor", "ceil", "fract", "sqrt", "exp", "log",
  "sin", "cos", "tan", "asin", "acos", "normalize",
]);
const SHAPE_JOIN = new Set(["min", "max", "clamp", "mix", "smoothstep", "mod", "pow"]);

function joinShapes(shapes) {
  let width = null;
  for (const shape of shapes) {
    if (shape === null) return null;
    if (typeof shape === "number") {
      if (width !== null && width !== shape) return null;
      width = shape;
    }
  }
  return width === null ? "s" : width;
}

/** Collect declared names and their types; a name declared with conflicting types maps to null. */
function collectDeclarations(statement, types) {
  if (!statement || typeof statement !== "object") {
    return;
  }
  switch (statement.type) {
    case "var": {
      const shape = shapeOfType(statement.varType);
      if (types.has(statement.name) && types.get(statement.name) !== shape) {
        types.set(statement.name, null);
      } else {
        types.set(statement.name, shape);
      }
      return;
    }
    case "block":
      for (const child of statement.body) {
        collectDeclarations(child, types);
      }
      return;
    case "if":
      collectDeclarations(statement.consequent, types);
      collectDeclarations(statement.alternate, types);
      return;
    case "for":
      collectDeclarations(statement.init, types);
      collectDeclarations(statement.body, types);
      return;
    default:
  }
}

const ARITH_HELPERS = { "+": "add", "-": "sub", "*": "mul", "/": "div" };

/**
 * Per-function emission state: the flat local namespace (mirroring the interpreter's single
 * call scope) with each name's declared shape, plus allocators for hoisted temps/guards.
 */
class FunctionEmitter {
  constructor(context, fn, name) {
    this.context = context;
    this.fn = fn;
    this.name = name;
    this.types = new Map();
    for (const param of fn.params) {
      this.types.set(param.name, shapeOfType(param.type));
    }
    collectDeclarations(fn.body, this.types);
    this.tempCount = 0;
    this.guardCount = 0;
  }

  temp() {
    const name = `t${this.tempCount}`;
    this.tempCount += 1;
    return name;
  }

  guard() {
    const name = `g${this.guardCount}`;
    this.guardCount += 1;
    return name;
  }

  isLocal(name) {
    return this.types.has(name);
  }

  /** Read reference for an identifier -- local, else global, else refuse to compile. */
  readRef(name) {
    if (this.isLocal(name)) {
      return `l_${name}`;
    }
    if (this.context.globalTypes.has(name)) {
      return `G[${nameLiteral(name)}]`;
    }
    // The interpreter would throw "Unknown GLSL identifier" at runtime; falling back gives
    // the model that exact behavior instead of a silent `undefined`.
    unsupported(`unknown identifier ${name}`);
    return "";
  }

  shapeOfName(name) {
    if (this.isLocal(name)) {
      return this.types.get(name);
    }
    return this.context.globalTypes.get(name) ?? null;
  }

  /**
   * Store `value` into `name`, mirroring Scope.set/define: the STORED value is cloned.
   * cloneValue is an identity on scalars, and a fresh castValue result cannot alias
   * anything, so the wrapper is dropped in exactly those cases.
   */
  writeStmt(name, valueExpr, { shape = null, fresh = false } = {}) {
    const needsClone = !fresh && shape !== "s";
    const stored = needsClone ? `H.cloneValue(${valueExpr})` : valueExpr;
    return `${this.readRef(name)} = ${stored}`;
  }

  /** Arithmetic + - * / with typed inlining; helper call whenever shapes are uncertain. */
  emitArith(op, left, right) {
    if (left.shape === "s" && right.shape === "s") {
      // mapBinary's scalar-scalar path is fn(a, b) -- the raw operator, same bits.
      return { code: `(${left.code} ${op} ${right.code})`, shape: "s" };
    }
    if (typeof left.shape === "number" && (right.shape === "s" || left.shape === right.shape)) {
      const a = this.temp();
      const b = this.temp();
      const width = left.shape;
      const component = (i) => (right.shape === "s"
        ? `${a}[${i}] ${op} ${b}`
        : `${a}[${i}] ${op} ${b}[${i}]`);
      const parts = Array.from({ length: width }, (_, i) => component(i)).join(", ");
      // Same evaluation order as helper arguments (left, then right), each once; equal
      // widths mean mapBinary's `?? 0` fills were no-ops, so components are identical ops.
      return { code: `(${a} = ${left.code}, ${b} = ${right.code}, [${parts}])`, shape: width };
    }
    if (left.shape === "s" && typeof right.shape === "number") {
      const a = this.temp();
      const b = this.temp();
      const parts = Array.from({ length: right.shape }, (_, i) => `${a} ${op} ${b}[${i}]`).join(", ");
      return { code: `(${a} = ${left.code}, ${b} = ${right.code}, [${parts}])`, shape: right.shape };
    }
    const width = typeof left.shape === "number"
      ? (typeof right.shape === "number" ? Math.max(left.shape, right.shape) : left.shape)
      : (typeof right.shape === "number" ? right.shape : null);
    return { code: `H.${ARITH_HELPERS[op]}(${left.code}, ${right.code})`, shape: width };
  }

  emitExpression(node) {
    switch (node.type) {
      case "literal":
        // Interpreter: cloneValue(node.value) -- identity for tokenizer numbers/bools.
        return { code: numberLiteral(node.value), shape: "s" };
      case "identifier":
        return { code: this.readRef(node.name), shape: this.shapeOfName(node.name) };
      case "member": {
        const object = this.emitExpression(node.object);
        const property = String(node.property);
        const resultShape = property.length === 1 ? "s" : property.length;
        const indices = [...property].map((c) => ({ x: 0, y: 1, z: 2, w: 3, r: 0, g: 1, b: 2, a: 3, s: 0, t: 1, p: 2, q: 3 })[c]);
        const valid = indices.every((i) => i !== undefined)
          && typeof object.shape === "number"
          && indices.every((i) => i < object.shape);
        if (!valid) {
          return {
            code: `H.getSwizzle(${object.code}, ${nameLiteral(node.property)})`,
            shape: indices.every((i) => i !== undefined) ? resultShape : null,
          };
        }
        if (indices.length === 1) {
          // In-range single component of a known-width vec: `source[i] ?? 0` never hits 0.
          return { code: `(${object.code})[${indices[0]}]`, shape: "s" };
        }
        const t = this.temp();
        const parts = indices.map((i) => `${t}[${i}]`).join(", ");
        return { code: `(${t} = ${object.code}, [${parts}])`, shape: resultShape };
      }
      case "unary": {
        const value = this.emitExpression(node.argument);
        if (node.op === "-") {
          if (value.shape === "s") {
            return { code: `(-(${value.code}))`, shape: "s" };
          }
          if (typeof value.shape === "number") {
            const t = this.temp();
            const parts = Array.from({ length: value.shape }, (_, i) => `-${t}[${i}]`).join(", ");
            return { code: `(${t} = ${value.code}, [${parts}])`, shape: value.shape };
          }
          return { code: `H.neg(${value.code})`, shape: value.shape };
        }
        if (node.op === "!") {
          return { code: `(!H.truthy(${value.code}))`, shape: "s" };
        }
        // Interpreter returns the value unchanged for any other unary op (e.g. `+`).
        return { code: `(${value.code})`, shape: value.shape };
      }
      case "update": {
        // Mirror: current = get; next = add/sub(current, 1); store(next); value is `next`
        // (prefix) or `current` (postfix), un-cloned.
        if (node.argument?.type !== "identifier") {
          unsupported("update of a non-identifier");
        }
        const shape = this.shapeOfName(node.argument.name);
        const current = this.temp();
        const next = this.temp();
        const read = this.readRef(node.argument.name);
        const step = shape === "s"
          ? `${next} = ${current} ${node.op === "++" ? "+" : "-"} 1`
          : `${next} = H.${node.op === "++" ? "add" : "sub"}(${current}, 1)`;
        const write = this.writeStmt(node.argument.name, next, { shape });
        return {
          code: `(${current} = ${read}, ${step}, ${write}, ${node.prefix ? next : current})`,
          shape,
        };
      }
      case "binary": {
        // && / || short-circuit through truthy, exactly as the interpreter special-cases
        // them; native JS laziness matches.
        if (node.op === "&&" || node.op === "||") {
          const left = this.emitExpression(node.left);
          const right = this.emitExpression(node.right);
          return { code: `(H.truthy(${left.code}) ${node.op} H.truthy(${right.code}))`, shape: "s" };
        }
        const left = this.emitExpression(node.left);
        const right = this.emitExpression(node.right);
        if (ARITH_HELPERS[node.op]) {
          return this.emitArith(node.op, left, right);
        }
        switch (node.op) {
          case "<": case ">": case "<=": case ">=":
            return { code: `(${left.code} ${node.op} ${right.code})`, shape: "s" };
          // The interpreter's `===`/`!==` on raw values: reference equality for vecs.
          case "==": return { code: `(${left.code} === ${right.code})`, shape: "s" };
          case "!=": return { code: `(${left.code} !== ${right.code})`, shape: "s" };
          default:
            unsupported(`operator ${node.op}`);
        }
        return { code: "", shape: null };
      }
      case "ternary": {
        const condition = this.emitExpression(node.condition);
        const consequent = this.emitExpression(node.consequent);
        const alternate = this.emitExpression(node.alternate);
        return {
          code: `(H.truthy(${condition.code}) ? ${consequent.code} : ${alternate.code})`,
          shape: consequent.shape === alternate.shape ? consequent.shape : null,
        };
      }
      case "assign":
        return this.emitAssign(node);
      case "call": {
        const callee = node.callee?.type === "identifier" ? node.callee.name : "";
        const args = node.args.map((arg) => this.emitExpression(arg));
        const argCode = args.map((arg) => arg.code).join(", ");
        // Builtins shadow user functions, exactly as the interpreter checks BUILTINS first.
        if (this.context.builtins[callee]) {
          this.context.usedBuiltins.add(callee);
          let shape = null;
          if (SCALAR_BUILTINS.has(callee)) {
            shape = "s";
          } else if (callee in CONSTRUCTOR_SHAPES) {
            shape = CONSTRUCTOR_SHAPES[callee];
          } else if (SHAPE_PRESERVING.has(callee)) {
            shape = args[0]?.shape ?? null;
          } else if (SHAPE_JOIN.has(callee)) {
            shape = joinShapes(args.map((arg) => arg.shape));
          }
          return { code: `B_${callee}(${argCode})`, shape };
        }
        if (this.context.functionShapes.has(callee)) {
          return { code: `f_${callee}(${argCode})`, shape: this.context.functionShapes.get(callee) };
        }
        unsupported(`unknown function ${callee}`);
        return { code: "", shape: null };
      }
      default:
        unsupported(`expression node ${node?.type}`);
        return { code: "", shape: null };
    }
  }

  emitAssign(node) {
    const right = this.temp();
    const rightExpr = this.emitExpression(node.right);
    // Compound value: op(current, right); the right side evaluates BEFORE current is read,
    // exactly as the interpreter builds the lvalue, evaluates the right, then calls get().
    const combine = (currentCode, currentShape) => {
      if (node.op === "=") {
        return { code: right, shape: rightExpr.shape };
      }
      const op = { "+=": "+", "-=": "-", "*=": "*" }[node.op] ?? "/";
      return this.emitArith(op, { code: currentCode, shape: currentShape }, { code: right, shape: rightExpr.shape });
    };
    if (node.left?.type === "identifier") {
      const name = node.left.name;
      const combined = combine(this.readRef(name), this.shapeOfName(name));
      const value = this.temp();
      const write = this.writeStmt(name, value, { shape: combined.shape });
      return {
        code: `(${right} = ${rightExpr.code}, ${value} = ${combined.code}, ${write}, ${value})`,
        shape: combined.shape,
      };
    }
    if (node.left?.type === "member" && node.left.object?.type === "identifier") {
      // Mirror the member lvalue: mutate the LIVE array via setSwizzle, then re-store a
      // clone of it (Scope.set), evaluating to the un-cloned assigned value.
      const name = node.left.object.name;
      const target = this.temp();
      const value = this.temp();
      const property = nameLiteral(node.left.property);
      const currentShape = String(node.left.property).length === 1 ? "s" : String(node.left.property).length;
      const combined = combine(`H.getSwizzle(${target}, ${property})`, currentShape);
      const write = this.writeStmt(name, target, { shape: this.shapeOfName(name) });
      return {
        code: `(${right} = ${rightExpr.code}, ${target} = ${this.readRef(name)}, ${value} = ${combined.code}, ` +
          `H.setSwizzle(${target}, ${property}, ${value}), ${write}, ${value})`,
        shape: combined.shape,
      };
    }
    unsupported("assignment target");
    return { code: "", shape: null };
  }

  emitStatement(statement) {
    switch (statement.type) {
      case "empty":
        return ";";
      case "block":
        // Braces only; NO scope -- every declaration was hoisted to the function head, so
        // sibling blocks share names exactly as the interpreter's shared call scope does.
        return `{\n${statement.body.map((child) => this.emitStatement(child)).join("\n")}\n}`;
      case "var": {
        if (!statement.init) {
          unsupported("var without initializer");
        }
        // define(castValue(init, type)): castValue returns a primitive or a FRESH vec, so
        // the define-side clone is an identity either way and is dropped.
        const cast = `H.castValue(${this.emitExpression(statement.init).code}, ${nameLiteral(statement.varType)})`;
        return `${this.writeStmt(statement.name, cast, { fresh: true })};`;
      }
      case "expr":
        return `${this.emitExpression(statement.expression).code};`;
      case "return":
        if (!statement.expression) {
          unsupported("bare return");
        }
        // The interpreter casts at the call boundary; casting at each return site is the
        // same value on every path.
        return `return H.castValue(${this.emitExpression(statement.expression).code}, ${nameLiteral(this.fn.returnType)});`;
      case "if": {
        const consequent = this.emitStatement(statement.consequent);
        const alternate = statement.alternate ? ` else ${this.emitStatement(statement.alternate)}` : "";
        return `if (H.truthy(${this.emitExpression(statement.condition).code})) ${consequent}${alternate}`;
      }
      case "break":
        return "break;";
      case "continue":
        return "continue;";
      case "for": {
        // Mirror of the interpreter's guarded loop: init once into the SAME namespace (the
        // counter outlives the loop), condition through truthy, the model's update in the
        // JS update slot so native `continue` still runs it, and the exporter safety guard
        // throwing the interpreter's exact message after 10,000 iterations.
        const guard = this.guard();
        const init = statement.init ? this.emitStatement(statement.init) : ";";
        const update = statement.update
          ? `(${this.emitExpression(statement.update).code}, ${guard} += 1)`
          : `${guard} += 1`;
        const condition = statement.condition
          ? `if (!H.truthy(${this.emitExpression(statement.condition).code})) break;\n`
          : "";
        return `${init}\n${guard} = 0;\n` +
          `for (;; ${update}) {\n` +
          `if (${guard} >= 10000) { throw new Error("GLSL for-loop exceeded exporter safety limit"); }\n` +
          `${condition}${this.emitStatement(statement.body)}\n}`;
      }
      default:
        unsupported(`statement node ${statement?.type}`);
        return "";
    }
  }

  emit() {
    const params = this.fn.params.map((param, index) => `a${index}`);
    // define(param, castValue(arg, type)): castValue's result is fresh, so the define-side
    // clone is dropped, matching the var-declaration reasoning.
    const paramInit = this.fn.params.map((param, index) =>
      `let l_${param.name} = H.castValue(a${index}, ${nameLiteral(param.type)});`);
    const body = this.emitStatement(this.fn.body);
    const paramNames = new Set(this.fn.params.map((param) => param.name));
    const hoisted = [...this.types.keys()].filter((name) => !paramNames.has(name));
    const declarations = [
      ...(hoisted.length ? [`let ${hoisted.map((name) => `l_${name}`).join(", ")};`] : []),
      ...(this.tempCount ? [`let ${Array.from({ length: this.tempCount }, (_, i) => `t${i}`).join(", ")};`] : []),
      ...(this.guardCount ? [`let ${Array.from({ length: this.guardCount }, (_, i) => `g${i}`).join(", ")};`] : []),
    ];
    // Fallthrough without a return: the interpreter's call boundary returns the type's
    // default value.
    return `function f_${this.name}(${params.join(", ")}) {\n` +
      `${paramInit.join("\n")}\n${declarations.join("\n")}\n${body}\n` +
      `return H.defaultValueForType(${nameLiteral(this.fn.returnType)});\n}`;
  }
}

/** Global statements run once at factory time; reads/writes go to `G`, never to locals. */
class GlobalEmitter extends FunctionEmitter {
  constructor(context) {
    super(context, { params: [], body: { type: "block", body: [] }, returnType: "void" }, "globals");
    this.types = new Map();
  }

  readRef(name) {
    if (this.context.globalTypes.has(name)) {
      return `G[${nameLiteral(name)}]`;
    }
    unsupported(`unknown global identifier ${name}`);
    return "";
  }

  shapeOfName(name) {
    return this.context.globalTypes.get(name) ?? null;
  }
}

/**
 * Compile `source` into a runtime with the interpreter runtime's exact interface
 * (`{ call(name, args) }`), or return null if anything at all prevents it.
 *
 * `env` supplies the shared frontend and the helper/builtin function objects
 * (`implicitSdfEvaluatorInternals`); injecting it keeps this module dependency-free and
 * avoids an import cycle with the evaluator.
 */
export function compileImplicitProgramRuntime(model, source, entryName, env) {
  try {
    const { BUILTINS, tokenize, Parser, helpers } = env;
    const program = new Parser(tokenize(source)).parseProgram();
    // `inout` needs write-back into the caller's variable, which neither backend implements.
    // Decline so the interpreter path reports it -- compiling by value would silently return
    // wrong geometry, the one failure mode this compiler must never introduce.
    for (const fn of program.functions.values()) {
      if (fn.params?.some((param) => param.qualifiers?.includes("inout"))) {
        return null;
      }
    }
    if (!program.functions.has(entryName)) {
      // Let the interpreter path produce its canonical "did not define" error.
      return null;
    }

    // The shared mutable global store, mirroring the interpreter's globals Scope: PI and
    // TWO_PI, then the model's uniforms cast+cloned once, then the program's own globals
    // (initialized below, inside the factory, so they may call user functions).
    const G = Object.create(null);
    G.PI = Math.PI;
    G.TWO_PI = Math.PI * 2;
    const globalTypes = new Map([["PI", "s"], ["TWO_PI", "s"]]);
    for (const [name, uniform] of Object.entries(model?.uniforms || {})) {
      G[name] = helpers.cloneValue(helpers.castValue(uniform?.value, uniform?.type));
      globalTypes.set(name, shapeOfType(uniform?.type));
    }
    for (const statement of program.globals) {
      collectDeclarations(statement, globalTypes);
    }

    const functionShapes = new Map(
      [...program.functions.entries()].map(([name, fn]) => [name, shapeOfType(fn.returnType)])
    );
    const context = {
      builtins: BUILTINS,
      usedBuiltins: new Set(),
      functionShapes,
      globalTypes,
    };

    const functionSources = [];
    for (const [name, fn] of program.functions.entries()) {
      functionSources.push(new FunctionEmitter(context, fn, name).emit());
    }
    const globalEmitter = new GlobalEmitter(context);
    const globalSources = program.globals.map((statement) => globalEmitter.emitStatement(statement));
    const globalTemps = [
      ...(globalEmitter.tempCount ? [`let ${Array.from({ length: globalEmitter.tempCount }, (_, i) => `t${i}`).join(", ")};`] : []),
      ...(globalEmitter.guardCount ? [`let ${Array.from({ length: globalEmitter.guardCount }, (_, i) => `g${i}`).join(", ")};`] : []),
    ];

    const builtinConsts = [...context.usedBuiltins].map(
      (name) => `const B_${name} = BUILTINS[${nameLiteral(name)}];`
    );
    const table = [...program.functions.keys()].map(
      (name) => `${nameLiteral(name)}: f_${name}`
    );

    const factorySource = `"use strict";\n${builtinConsts.join("\n")}\n` +
      `${functionSources.join("\n")}\n${globalTemps.join("\n")}\n${globalSources.join("\n")}\n` +
      `return { ${table.join(", ")} };`;

    // eslint-disable-next-line no-new-func -- the whole point of this module.
    const factory = new Function("H", "BUILTINS", "G", factorySource);
    const functions = factory(helpers, BUILTINS, G);

    return {
      compiled: true,
      call(name, args) {
        const fn = functions[name];
        if (!fn) {
          throw new Error(`Unknown GLSL function: ${name}`);
        }
        return fn(...args);
      },
    };
  } catch {
    // ANY failure -- parse, unsupported construct, codegen bug caught by `new Function` --
    // means the interpreter handles this model. Slow is acceptable; wrong is not.
    return null;
  }
}
