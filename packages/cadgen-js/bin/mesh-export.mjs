#!/usr/bin/env node
/**
 * Mesh-export a render package: assembly.json + component surfs -> one
 * STL/GLB/3MF file (design/unified-tessellation.md Phase 3).
 *
 * This is the ONE mesh export path: components tessellate from their exact
 * surfaces through the same watertight tessellator the viewport uses, at the
 * same default tolerances, so an export IS what rendered. cadgen's
 * step_export_target dispatches its stl/3mf/glb arms here; `.step` stays
 * native blob assembly and never meshes.
 *
 * Contract:
 *   node mesh-export.mjs --package-dir <abs dir> \
 *     --format stl|glb|3mf --out <abs path> [--chord-tolerance t] [--angle-tolerance t] \
 *       [--animation '{"clip":...}'] \
 *     [--format F --out P [--chord-tolerance t] [--angle-tolerance t] ...] \
 *     [--name N] [--render-module <abs path>]
 *   `--format`/`--out` repeat as ordered pairs. Tolerance and animation flags
 *   AFTER a pair bind to that pair; tolerance flags BEFORE the first pair set
 *   the run defaults. Jobs group by their effective tolerance pair: the package
 *   is tessellated ONCE PER GROUP and each job serializes from its group's
 *   tessellation, so same-tolerance formats share one tessellation exactly as
 *   before. stdout is exactly one JSON line:
 *   {"ok":true,"files":[{"path":...,"format":...,"triangleCount":...},...]}
 *   or {"ok":false,"error":...}. No locks, no progress protocol — this writes
 *   only the files the caller named (plus best-effort cache entries).
 *
 * `--animation` is the GLB door's clip request, `{clip, fps, seconds, start,
 * drop, deform, deformTolerance}` — the same shape cadgen's mesh_animation
 * normalized before spawning this. The choreography is the render module beside
 * the DOCUMENT (`<name>.step.js`, passed as `--render-module`), compiled through
 * the one loader the viewer uses, sampled into per-occurrence keyframes, and
 * written as glTF animation. An animated job emits one node per occurrence
 * instead of the flat colour-grouped soup, because a channel needs a node to
 * target. With `deform: "morph"` a deforming tube's node also carries baked
 * MORPH TARGETS and a weights channel (lib/export/packageTubeMorph.js), which
 * replaces that occurrence's geometry with the refined, posed mesh the targets
 * are deltas against.
 *
 * Component tessellations are cached under <cache root>/meshes/ (root:
 * CADGEN_CACHE_DIR, else the platform cache dir — see tessellationCacheFs.mjs)
 * keyed <cid>-t<tessellator-version>-l<chord>-a<angle> (tolerances in the
 * tessellator's diagonal-relative units), so repeat exports and
 * multi-occurrence assemblies pay tessellation once per unique component. The
 * cache is BEST-EFFORT: read/write failures fall through to tessellation,
 * writes are atomic (tmp + rename), and CADGEN_MESH_CACHE=0 disables it
 * entirely; `cadgen cache gc` sweeps orphaned generations.
 */

import fs from "node:fs";
import path from "node:path";

import { parseSurf } from "../src/lib/surf/container.js";
import { DEFAULT_OPTIONS, tessellateComponent } from "../src/lib/surf/tessellate.js";
import {
  decodeComponentTessellation,
  edgeClassesFromSurfIndex,
  encodeComponentTessellation,
  tessellationCacheKey,
} from "../src/lib/surf/tessellationCache.js";
import {
  readCachedTessellationBytes,
  writeCachedTessellationBytes,
} from "../src/lib/surf/tessellationCacheFs.mjs";
import {
  PACKAGE_MESH_EXPORT_FORMATS,
  buildPackageMeshPrimitives,
  packageMeshToFormat,
} from "../src/lib/export/packageMeshExport.js";
import {
  restrictAnimationToNodes,
  sampleClipAnimation,
  withMorphChannels,
} from "../src/lib/export/packageAnimation.js";
import { buildTubeMorphTargets } from "../src/lib/export/packageTubeMorph.js";
import { animationClipList, findAnimationClip } from "../src/common/animationClock.js";
import { resolveFramePlan } from "../src/common/framePlan.js";
import { compileRenderModule, importRenderModule } from "../src/common/renderModule.js";

function parseArgs(argv) {
  // Scalar flags are last-wins; `--format`/`--out` collect in CLI order and
  // zip into export pairs. Tolerance flags bind to the most recent pair, or
  // set the run defaults when they appear before any pair.
  const args = {};
  const formats = [];
  const outs = [];
  const pairTolerances = [];
  const pairAnimations = [];
  const defaults = { chord: undefined, angle: undefined };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    const value = next === undefined || next.startsWith("--") ? "true" : next;
    if (value !== "true") index += 1;
    if (token === "--format") {
      formats.push(value);
      pairTolerances.push({ chord: undefined, angle: undefined });
      pairAnimations.push(undefined);
    } else if (token === "--out") {
      outs.push(value);
    } else if (token === "--chord-tolerance") {
      (pairTolerances.length ? pairTolerances[pairTolerances.length - 1] : defaults).chord = value;
    } else if (token === "--angle-tolerance") {
      (pairTolerances.length ? pairTolerances[pairTolerances.length - 1] : defaults).angle = value;
    } else if (token === "--animation") {
      // Job-scoped only: a clip is a property of ONE output, and a run default
      // would silently animate every format in the run, two of which cannot
      // carry it at all.
      if (!pairAnimations.length) {
        fail("--animation must follow the --format/--out pair it animates");
      }
      pairAnimations[pairAnimations.length - 1] = value;
    } else {
      args[token.slice(2)] = value;
    }
  }
  return { args, formats, outs, pairTolerances, pairAnimations, defaults };
}

function fail(message) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: String(message) })}\n`);
  process.exit(1);
}

function tessellationForComponent(packageDir, cid, entry, options) {
  const key = tessellationCacheKey(cid, options);
  const cached = decodeComponentTessellation(readCachedTessellationBytes(key));
  if (cached) {
    return { ...cached.component, partColor: cached.partColor };
  }
  const surfRel = String(entry?.surf || "");
  if (!surfRel) throw new Error(`component ${cid} has no surf payload`);
  const bytes = fs.readFileSync(path.join(packageDir, surfRel));
  const { index, floats } = parseSurf(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
  const component = tessellateComponent(index, floats, options);
  const partColor = Array.isArray(index.partColor) ? index.partColor : null;
  writeCachedTessellationBytes(
    key,
    encodeComponentTessellation(component, {
      partColor,
      edgeClasses: edgeClassesFromSurfIndex(index),
    }),
  );
  return { ...component, partColor };
}

const { args, formats, outs, pairTolerances, pairAnimations, defaults } = parseArgs(process.argv.slice(2));
const packageDir = String(args["package-dir"] || "");
if (!packageDir || !path.isAbsolute(packageDir)) {
  fail("--package-dir must be an absolute render-package directory");
}
if (!formats.length || formats.length !== outs.length) {
  fail("--format and --out must be given as one or more ordered pairs");
}
const jobs = formats.map((rawFormat, index) => {
  const chord = pairTolerances[index].chord ?? defaults.chord;
  const angle = pairTolerances[index].angle ?? defaults.angle;
  const options = { ...DEFAULT_OPTIONS };
  if (chord !== undefined) options.chordTolerance = Number(chord);
  if (angle !== undefined) options.angleTolerance = Number(angle);
  let animation = null;
  if (pairAnimations[index] !== undefined) {
    try {
      animation = JSON.parse(String(pairAnimations[index]));
    } catch (error) {
      fail(`--animation must be a JSON object: ${error?.message || error}`);
    }
    if (!animation || typeof animation !== "object" || Array.isArray(animation)) {
      fail("--animation must be a JSON object");
    }
  }
  return {
    format: String(rawFormat).toLowerCase(),
    out: String(outs[index]),
    options,
    animation,
    // Tessellation-group identity: jobs sharing an effective pair share one
    // tessellation of the tree and one primitive build.
    groupKey: `${options.chordTolerance}:${options.angleTolerance}`,
  };
});
for (const job of jobs) {
  if (!job.out || !path.isAbsolute(job.out)) {
    fail("--out must be an absolute output path");
  }
  if (!PACKAGE_MESH_EXPORT_FORMATS.includes(job.format)) {
    fail(`--format must be one of ${PACKAGE_MESH_EXPORT_FORMATS.join(", ")}`);
  }
  if (!(job.options.chordTolerance > 0) || !(job.options.angleTolerance > 0)) {
    fail("tolerances must be positive numbers");
  }
  if (job.animation && job.format !== "glb") {
    fail(`${job.format} carries no animation: only glb does`);
  }
  if (job.animation && !String(job.animation.clip || "").trim()) {
    fail("--animation must name a clip");
  }
}
if (new Set(jobs.map((job) => job.out)).size !== jobs.length) {
  fail("--out paths must be distinct");
}
const name = String(args.name || path.basename(jobs[0].out).replace(/\.[^.]+$/, "") || "model");
const defaultColor = args["default-color"] ? String(args["default-color"]) : null;
if (defaultColor !== null && !/^#[0-9a-fA-F]{6}$/.test(defaultColor)) {
  fail("--default-color must be #rrggbb");
}

const renderModulePath = String(args["render-module"] || "");
if (jobs.some((job) => job.animation) && !renderModulePath) {
  fail("--animation needs --render-module: the clips live in the .step.js beside the document");
}

/** The document's compiled clips, through the ONE render-module loader.
 *
 * `loadRenderModule` fetches; this reads the file the caller named, because a
 * builder has the path and no HTTP. Everything after the read is shared — the
 * same Blob-realm import, the same closed export vocabulary — so a module the
 * viewer refuses is a module this refuses, with the same message.
 */
async function loadClips(modulePath) {
  const source = fs.readFileSync(modulePath, "utf8");
  const moduleName = path.basename(modulePath);
  const namespace = await importRenderModule(source, { name: moduleName });
  return compileRenderModule(namespace, { name: moduleName }).clips;
}

/** One job's sampled clip: the schedule it resolved and the tracks it baked. */
function sampleJobAnimation(job, clips, descriptor) {
  const clipName = String(job.animation.clip);
  const clip = findAnimationClip(clips, clipName);
  if (!clip) {
    const declared = animationClipList(clips).map((entry) => entry.id);
    throw new Error(
      declared.length
        ? `Unknown animation clip: ${clipName}. This model declares: ${declared.join(", ")}`
        : `Unknown animation clip: ${clipName}. This model declares no animation clips`,
    );
  }
  const plan = resolveFramePlan(job.animation, clip, { label: "animation" });
  const sampled = sampleClipAnimation(descriptor, clip, plan, {
    drop: Array.isArray(job.animation.drop) ? job.animation.drop : [],
    deform: job.animation.deform,
  });
  return { clip, plan, sampled };
}

try {
  const descriptor = JSON.parse(fs.readFileSync(path.join(packageDir, "assembly.json"), "utf8"));
  const componentEntries = descriptor.components || {};
  const used = new Set(
    (descriptor.occurrences || []).map((occurrence) => String(occurrence.component || "")),
  );
  // Compiled only when a job actually asks for a clip: a render module is a
  // file the caller may name for other reasons, and a syntax error in one must
  // not fail a static export that never reads it.
  const clips = jobs.some((job) => job.animation) ? await loadClips(renderModulePath) : null;
  const groups = new Map();
  jobs.forEach((job, index) => {
    if (!groups.has(job.groupKey)) groups.set(job.groupKey, { options: job.options, members: [] });
    groups.get(job.groupKey).members.push({ job, index });
  });
  const files = [];
  for (const group of groups.values()) {
    const tessellations = new Map();
    for (const cid of used) {
      if (!componentEntries[cid]) throw new Error(`descriptor names unknown component ${cid}`);
      tessellations.set(
        cid,
        tessellationForComponent(packageDir, cid, componentEntries[cid], group.options),
      );
    }
    const colorOption = defaultColor ? { defaultColor: defaultColor.toLowerCase() } : {};
    // Primitives are per tolerance group: every static job in the group shares one
    // tessellation and one primitive build of the tree as stored. An ANIMATED job
    // builds its own, because its node layout is per occurrence and the effects its
    // clip drops (a hidden occurrence, a faded one) change which primitives exist.
    let staticMesh = null;
    for (const { job, index } of group.members) {
      let mesh;
      let animation = null;
      let summary = null;
      if (job.animation) {
        const { plan, sampled } = sampleJobAnimation(job, clips, descriptor);
        // The deformation bake runs BEFORE the primitive build, because it replaces
        // a deforming tube's geometry outright: the base mesh a morph target is a
        // delta against is the REFINED, POSED tube, not the rest tessellation the
        // soup path would have placed.
        const morph = buildTubeMorphTargets(descriptor, tessellations, sampled.deformations, {
          toleranceMm: job.animation.deformTolerance,
          grid: sampled.grid,
          clipId: sampled.name,
          ...(colorOption.defaultColor ? { defaultColor: colorOption.defaultColor } : {}),
        });
        mesh = buildPackageMeshPrimitives(descriptor, tessellations, {
          ...colorOption,
          perOccurrence: true,
          hiddenOccurrenceIds: sampled.statics.hidden,
          occurrenceOpacity: sampled.statics.opacity,
          occurrenceOverrides: morph.overrides,
        });
        // The sampler worked from the descriptor's occurrence table; the file's
        // nodes are what came out of the tessellation. Reconcile the two before
        // the writer does, so an occurrence with no geometry is a named warning
        // rather than a glTF invariant thrown at the user.
        animation = restrictAnimationToNodes(
          withMorphChannels(sampled, morph.channels),
          new Set(mesh.primitives.map((primitive) => primitive.node).filter(Boolean)),
        );
        summary = {
          clip: animation.name,
          fps: plan.fps,
          samples: plan.frameCount,
          seconds: plan.seconds,
          start: plan.start,
          channels: animation.channels.length,
          ...(morph.stats ? {
            deform: {
              mode: "morph",
              nodes: morph.stats.nodes,
              targets: morph.stats.targets,
              bytes: morph.stats.bytes,
              runtimeBytes: morph.stats.runtimeBytes,
              refinedTriangles: morph.stats.refinedTriangles,
              deviationMm: Number(morph.stats.deviationMm.toFixed(4)),
              toleranceMm: morph.stats.toleranceMm,
              fitGridHz: sampled.grid.hz,
            },
          } : {}),
          warnings: [...plan.warnings, ...animation.warnings, ...morph.warnings],
        };
      } else {
        staticMesh = staticMesh || buildPackageMeshPrimitives(descriptor, tessellations, colorOption);
        mesh = staticMesh;
      }
      if (!mesh.triangleCount) throw new Error("tree produced no triangles");
      const { body } = packageMeshToFormat(mesh, job.format, { name, animation });
      fs.mkdirSync(path.dirname(job.out), { recursive: true });
      const temp = `${job.out}.${process.pid}.tmp`;
      fs.writeFileSync(temp, body);
      fs.renameSync(temp, job.out);
      files[index] = {
        path: job.out,
        format: job.format,
        triangleCount: mesh.triangleCount,
        ...(summary ? { animation: summary } : {}),
      };
    }
  }
  process.stdout.write(`${JSON.stringify({ ok: true, files })}\n`);
} catch (error) {
  fail(error?.message || error);
}
