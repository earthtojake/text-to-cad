import assert from "node:assert/strict";
import test from "node:test";
import { formatPromptMessage } from "@cad/core/prompt";

import { createViewPromptContext, subjectReference } from "./promptContext.js";

// A model's document, as the view names it (by its id), and what a share's host names it by instead.
const resource = { kind: "cad-model", path: "1024a2f2-2b65-5151-8299-282973f2a9fc", revision: "build 1" };
const face = { resource, target: { kind: "cad-selector", selectors: ["base/f:base.extrude1.2"] } };
const link = "https://cad.example/AbCdEfGhIjKlMnOpQrSt_-";
const subject = { resource: { kind: "url", url: link } };
const capture = Promise.resolve(new Blob(["png"], { type: "image/png" }));

test("a screenshot's prompt names the file as the host's prompts do: by its link, and says nothing more of it", () => {
  // The whole file, where nothing is picked.
  assert.equal(formatPromptMessage(createViewPromptContext({ resource, capture, subject })), `File: ${link}`);
  // What is picked, each reference into the file by its link, its target kept; the picture is about them.
  const picked = createViewPromptContext({ resource, references: [face], capture, subject });
  assert.equal(formatPromptMessage(picked), `References:\n${link}#base/f:base.extrude1.2`);
  assert.deepEqual(picked.parts.find(part => part.kind === "attachment").about, ["reference-0"]);
  // A host that names nothing otherwise: the file as the view names it, and no note.
  assert.equal(formatPromptMessage(createViewPromptContext({ resource, references: [face], capture })), `References:\n${resource.path}#base/f:base.extrude1.2`);
  assert.equal(formatPromptMessage(createViewPromptContext({ resource, capture })), `File: ${resource.path}`);
});

test("only a reference into the document on screen takes the host's name for it", () => {
  const other = { resource: { kind: "workspace-file", path: "/m/other.step" }, target: { kind: "cad-selector", selectors: ["plate/face 1"] } };
  assert.equal(subjectReference(other, resource, subject), other);
  // The document on screen at another revision is the same document.
  assert.deepEqual(subjectReference(face, { ...resource, revision: "build 2" }, subject), { ...face, resource: subject.resource });
  assert.equal(subjectReference(face, resource, {}), face);
  assert.equal(subjectReference(face, resource, null), face);
});
