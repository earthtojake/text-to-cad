import assert from "node:assert/strict";
import { test, after } from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";

const temporary = await mkdtemp(join(tmpdir(), "hardcore-registry-test-"));
const output = join(temporary, "registry.mjs");
await build({ entryPoints: [fileURLToPath(new URL("./registry.ts", import.meta.url))], bundle: true, platform: "node", format: "esm", outfile: output });
const { defineFileRenderer, selectRenderer, validateRenderers } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));
const file = { path: "notes.md", name: "notes.md", kind: "file", extension: "md", size: 4, mediaType: "text" };
const source = { id: "root-a", rootName: "A", stat: async () => file };
const registration = (id, priority, matches = () => true, fallback = false) => defineFileRenderer({
  id, priority, matches, fallback, prepare: async () => ({ data: "typed payload" }), load: async () => ({ default: () => null }),
});

test("specific registrations precede generic text, with explicit fallback", () => {
  const generic = registration("text", 0), markdown = registration("markdown", 100), fallback = registration("unsupported", -100, () => false, true);
  assert.equal(selectRenderer([generic, fallback, markdown], file).id, "markdown");
  assert.equal(selectRenderer([registration("never", 1, () => false), fallback], file).id, "unsupported");
  assert.throws(() => selectRenderer([registration("never", 1, () => false)], file), /No registered renderer/);
});
test("duplicates, ambiguous matches and invalid fallback sets fail usefully", () => {
  assert.throws(() => validateRenderers([registration("same", 1), registration("same", 2)]), /Duplicate/);
  assert.throws(() => selectRenderer([registration("a", 1), registration("b", 1)], file), /Ambiguous.*a.*b/);
  assert.throws(() => validateRenderers([registration("a", 1, undefined, true), registration("b", 2, undefined, true)]), /at most one/);
});
test("constructing and matching registrations never loads a component", async () => {
  let loads = 0;
  const renderer = defineFileRenderer({ id: "lazy", priority: 1, matches: () => true, prepare: async () => ({ data: 42 }), load: async () => { loads += 1; return { default: () => null }; } });
  assert.equal(selectRenderer([renderer], file), renderer);
  assert.equal(loads, 0);
  await renderer.prepare({ file, source, signal: new AbortController().signal });
  assert.equal(loads, 1);
});
test("late prepared resources are released after cancellation and loader failure", async () => {
  for (const scenario of ["abort", "loader-failure"]) {
    const controller = new AbortController();
    let released = 0;
    let finishPreparation;
    let started;
    const preparationStarted = new Promise(resolve => { started = resolve; });
    const preparation = new Promise(resolve => { finishPreparation = resolve; });
    const renderer = defineFileRenderer({
      id: scenario, priority: 1, matches: () => true,
      prepare: async () => { started(); await preparation; return { data: 1, dispose: () => { released += 1; } }; },
      load: async () => { if (scenario === "loader-failure") throw new Error("module unavailable"); return { default: () => null }; },
    });
    const pending = renderer.prepare({ file, source, signal: controller.signal });
    const rejected = assert.rejects(pending);
    await preparationStarted;
    if (scenario === "abort") controller.abort();
    await rejected;
    finishPreparation();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(released, 1);
  }
});

test("cancellation releases a prepared asset immediately while its module is still loading", async () => {
  const controller = new AbortController();
  let finishModule;
  let released = 0;
  const module = new Promise(resolve => { finishModule = resolve; });
  const renderer = defineFileRenderer({
    id: 'delayed-module', priority: 1, matches: () => true,
    prepare: async () => ({ data: 1, dispose: () => { released += 1; } }),
    load: () => module,
  });
  const pending = renderer.prepare({ file, source, signal: controller.signal });
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  await new Promise(resolve => setImmediate(resolve));
  controller.abort();
  assert.equal(released, 1);
  await rejected;
  finishModule({ default: () => null });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(released, 1);
});

test("an already cancelled document starts neither loading nor preparation", async () => {
  const controller = new AbortController(); controller.abort();
  let calls = 0;
  const renderer = defineFileRenderer({ id: 'cancelled', priority: 1, matches: () => true,
    prepare: async () => { calls += 1; return { data: 1 }; }, load: async () => { calls += 1; return { default: () => null }; },
  });
  await assert.rejects(renderer.prepare({ file, source, signal: controller.signal }), { name: 'AbortError' });
  assert.equal(calls, 0);
});
