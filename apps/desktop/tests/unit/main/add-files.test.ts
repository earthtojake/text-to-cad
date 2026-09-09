import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, expect, it } from "vitest";
import { addProjectFile } from "@main/explorer/add-files";

let sandbox: string, project: string, source: string;
beforeEach(async () => {
  const models = fileURLToPath(new URL("../../../../../models/", import.meta.url));
  await fs.mkdir(models, { recursive: true });
  sandbox = await fs.mkdtemp(path.join(models, ".add-files-test-"));
  project = path.join(sandbox, "project");
  await fs.mkdir(project);
  source = path.join(sandbox, "bracket.STP");
  await fs.writeFile(source, "ISO-10303-21;\nEND-ISO-10303-21;\n");
});
afterEach(async () => { await fs.rm(sandbox, { recursive: true, force: true }); });

it("copies a chosen external STEP, preserving original bytes and duplicate names even concurrently", async () => {
  const first = await addProjectFile(project, source);
  expect(first.path).toBe("bracket.STP");
  await fs.writeFile(path.join(project, first.path), "existing file");
  const copies = await Promise.all([addProjectFile(project, source), addProjectFile(project, source)]);
  expect(copies.map(copy => copy.path).sort()).toEqual(["bracket (2).STP", "bracket (3).STP"]);
  expect(await fs.readFile(path.join(project, first.path), "utf8")).toBe("existing file");
  const original = await fs.readFile(source, "utf8");
  expect(original).toBe("ISO-10303-21;\nEND-ISO-10303-21;\n");
  for (const copy of copies) expect(await fs.readFile(path.join(project, copy.path), "utf8")).toBe(original);
  expect((await fs.readdir(project)).some(name => name.startsWith("."))).toBe(false);
});
it("preserves an existing destination symlink and its external target", async () => {
  const outside = path.join(sandbox, "outside.STP");
  await fs.writeFile(outside, "keep this");
  await fs.symlink(outside, path.join(project, "bracket.STP"));
  expect((await addProjectFile(project, source)).path).toBe("bracket (2).STP");
  expect(await fs.readFile(outside, "utf8")).toBe("keep this");
});
it("accepts non-CAD and extensionless files, while rejecting directories", async () => {
  for (const name of ["notes.txt", "reference.png", "drawing.pdf", "part.py", "LICENSE", "custom.data"]) {
    const input = path.join(sandbox, name);
    await fs.writeFile(input, Buffer.from([0, 42, 255, 10]));
    expect((await addProjectFile(project, input)).path).toBe(name);
    expect(await fs.readFile(path.join(project, name))).toEqual(await fs.readFile(input));
  }
  const folder = path.join(sandbox, "folder.step");
  await fs.mkdir(folder);
  await expect(addProjectFile(project, folder)).rejects.toThrow("not a folder");
});
