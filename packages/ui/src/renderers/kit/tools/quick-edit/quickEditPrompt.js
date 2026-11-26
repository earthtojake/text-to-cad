import { DOCUMENT_TYPE_REGISTRY } from "@cad/core/lib/documentTypes.generated.js";
import { createPromptContext, formatPromptReference, parsePromptReference, promptAddress, referencePart, resolvePromptMessage, snapshotPacket,
  snapshotPacketText, textPart } from "@cad/core/prompt";
import { subjectReference } from "../../shell/promptContext.js";

const stem = path => String(path || "").split("/").pop().replace(/\.[^.]+$/, "") || "view";
const pathOf = resource => resource.kind === "url" ? new URL(resource.url).pathname : resource.path;
const stemOf = resource => stem(pathOf(resource));
// What draws the packet again: the file's document type's snapshot (`cad <type> snapshot`), the type read off
// the registry by the extension of the file the view shows; a model's document, which has no file of its own, is
// the xbf's.
const typeOf = path => {
  const name = String(path || "").split("/").pop().toLowerCase();
  const found = DOCUMENT_TYPE_REGISTRY.documentTypes.find(type => type.extensions.some(extension => name.endsWith(extension)));
  return found ? found.id : "xbf";
};
// Made the first time something reads it: no host carries the packet's bytes beside its text.
const lazy = start => {
  let started = null;
  return { then: (resolve, reject) => (started ??= Promise.resolve().then(start)).then(resolve, reject) };
};

/**
 * A paste into the note, line by line: each line that is a reference and nothing else — a file's
 * absolute path and the ids in it, `/models/base.step#f:base.make_box1.2`, as Copy References and a chip's click
 * write one — is that reference (into any file); a paste that is the annotation as its chip copies
 * it (its annotation JSON, whole) is `[{ annotation }]`; every other line stays text. A reference
 * within a sentence is the sentence's. A line that is what one of the box's chips copied (`copied`:
 * what it copied, to the chip — an annotation's file path) is `{ chip, token }`.
 *
 * @param {string} pasted
 * @returns {Array<string | import("@cad/core/prompt").PromptReference | { annotation: object }>}
 */
export function pastedLines(pasted, copied = null) {
  const text = String(pasted || "");
  // The annotation, as its chip copies it: its annotation file's JSON, over several lines.
  const whole = parsedJson(text);
  if (whole && !Array.isArray(whole) && Array.isArray(whole.marks) && typeof whole.units === "string") return [{ annotation: whole }];
  return text.split(/\r?\n/).map(line => (copied?.has(line.trim()) ? { chip: copied.get(line.trim()), token: line.trim() } : null)
    ?? parsePromptReference(line) ?? line);
}

const parsedJson = text => {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return null;
  try { return JSON.parse(trimmed); } catch { return null; }
};

/** A reference as one line of text, the way Copy References writes it: what tells two apart. */
export const referenceToken = reference => formatPromptReference(reference);

/** The selection a Quick Edit attaches: what is picked in the file, not the file itself, which it always attaches. */
export const quickEditSelection = references => references.filter(reference => reference.target.kind !== "whole-resource");

/**
 * A Quick Edit as one prompt context: what the person wrote, the file on screen (always), the selection in it
 * (`references`, in the prompt grammar), and, where there is a view (`snapshot`: the views the prompt carries, the
 * annotation and a board's references, read at the press), its snapshot packet, made in the page
 * (`snapshotPacket`) and carried inline, whole, after the references: the same for every host, whatever its size.
 * Nothing is written and no picture is rendered or attached. Built at the press.
 * `folders` (the host's promise of `{ start, home }`): the message names every file by them — relative to
 * the workspace, else `~/` — the packet's `input` too, so no message carries the person's home.
 * `notes`: what the view itself has to tell the agent with this message, each a line or two of plain
 * text (what a person changed from the view since the last message), said after what the person wrote
 * and before the file. `subject` (the host's `promptSubject`): what the host's prompts name the file by,
 * in place of `resource` for it, for each reference into it and for the packet's `input`.
 *
 * @param {{ resource: object, references?: object[], text: string,
 *   snapshot?: { views: { label: string }[], annotation?: object | null, references?: string[] } | null,
 *   notes?: readonly string[], viewUnavailable?: string, folders?: Promise<{ start?: string, home?: string }> | null,
 *   subject?: import("../../../../host/types.js").PromptSubject | null }} quickEdit
 */
export function createQuickEditContext({ resource, references = [], text, snapshot = null, viewUnavailable = "", folders = null, notes = [], subject = null }) {
  const named = reference => subjectReference(reference, resource, subject);
  const file = named({ resource: { ...resource }, target: { kind: "whole-resource" } });
  const parts = [
    textPart(String(text || "").trim(), "text"),
    ...notes.map(note => String(note || "").trim()).filter(Boolean).map((note, index) => textPart(note, `note-${index}`)),
    ...(viewUnavailable ? [textPart(`View replay unavailable: ${viewUnavailable}`, "view-unavailable")] : []),
    referencePart(file, "file"),
    ...quickEditSelection(references).map((reference, index) => referencePart(named({ ...reference, resource: { ...reference.resource } }), `reference-${index}`)),
  ];
  if (snapshot?.views?.length) {
    // Made now, of the views as they are; addressed once the host has said the folders its files are named by, its
    // `input` the file's address as `File:` names it (`promptAddress`).
    const type = typeOf(pathOf(resource));
    const made = snapshotPacket({ input: "", type, views: snapshot.views, annotation: snapshot.annotation ?? null,
      references: snapshot.references ?? null });
    const packet = Promise.resolve(folders).catch(() => null).then(where => snapshotPacketText({ ...made,
      input: promptAddress(file.resource, where && typeof where === "object" ? where : null) }));
    packet.catch(() => {});
    parts.push({ id: "snapshot", kind: "attachment", name: `${stemOf(resource)}-snapshot.json`, mimeType: "application/json",
      inlineText: packet.then(json => `Snapshot JSON (\`cad ${type} snapshot --job\`):\n\`\`\`json\n${json}\n\`\`\``),
      content: lazy(() => packet.then(json => new Blob([json], { type: "application/json" }))), about: ["file"] });
  }
  return createPromptContext(parts, undefined, folders ? { folders } : {});
}

/**
 * A Quick Edit as the person copies it: its references by their files' paths (from the workspace, else `~/`), and its
 * snapshot packet inline.
 * @returns {Promise<string>}
 */
export async function copiedQuickEdit(context) {
  return resolvePromptMessage(context);
}
