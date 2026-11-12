import { DOCUMENT_TYPE_REGISTRY } from "@cad/core/lib/documentTypes.generated.js";
import { createPromptContext, displayPath, formatPromptReference, parsePromptReference, referencePart, resolvePromptMessage, textPart } from "@cad/core/prompt";

const stem = path => String(path || "").split("/").pop().replace(/\.[^.]+$/, "") || "view";
const pathOf = resource => resource.kind === "url" ? new URL(resource.url).pathname : resource.path;
const stemOf = resource => stem(pathOf(resource));
// The command that draws the packet again: the file's document type's snapshot (`cad <type> snapshot`),
// the type read off the registry by the file's extension; a model's document, which has no file of its
// own, is the engine's.
const typeOf = path => {
  const name = String(path || "").split("/").pop().toLowerCase();
  const found = DOCUMENT_TYPE_REGISTRY.documentTypes.find(type => type.extensions.some(extension => name.endsWith(extension)));
  return found ? found.id : "model";
};
const snapshotCommand = resource => `cad ${typeOf(pathOf(resource))} snapshot --annotation`;
// Awaited the first time something reads it: a file is fetched only by a host that carries its bytes.
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
 * A Quick Edit as one prompt context: what the person wrote, the file on screen (always), the
 * selection in it (`references`, in the prompt grammar), and — once the host has made them
 * (`files`) — the current and drawn views with the annotation, inline
 * when small or named by the saved .snapshot.json path. No pictures are rendered or attached. Built at the press.
 * `folders` (the host's promise of `{ start, home }`): the message names every file by them — relative to
 * the workspace, else `~/` — the inline packet's `input` too, so no message carries the person's home.
 *
 * @param {{ resource: object, references?: object[], text: string, views?: { label: string }[],
 *   files?: Promise<{ snapshot?: string, inline?: string }> | null,
 *   read?: (path: string) => Promise<Blob>, folders?: Promise<{ start?: string, home?: string }> | null }} quickEdit
 */
export function createQuickEditContext({ resource, references = [], text, views = [], files = null, read = null, viewUnavailable = "", folders = null }) {
  const parts = [
    textPart(String(text || "").trim(), "text"),
    ...(viewUnavailable ? [textPart(`View replay unavailable: ${viewUnavailable}`, "view-unavailable")] : []),
    referencePart({ resource: { ...resource }, target: { kind: "whole-resource" } }, "file"),
    ...quickEditSelection(references).map((reference, index) => referencePart({ ...reference, resource: { ...reference.resource } }, `reference-${index}`)),
  ];
  if (files && views.length) {
    const name = stemOf(resource);
    const made = pick => { const path = files.then(pick); path.catch(() => {}); return path; };
    const path = made(result => result.snapshot || "");
    const known = Promise.resolve(folders).catch(() => null);
    const inlineText = made(result => typeof result.inline === "string"
      ? known.then(where => `Snapshot JSON (${snapshotCommand(resource)}):\n\`\`\`json\n${shownPacket(result.inline, where)}\n\`\`\``) : null);
    parts.push({ id: "snapshot", kind: "attachment", label: `Snapshot (${snapshotCommand(resource)})`,
      name: `${name}.snapshot.json`, mimeType: "application/json", path, inlineText,
      content: lazy(() => files.then(result => typeof result.inline === "string"
        ? new Blob([result.inline], { type: "application/json" }) : read(result.snapshot))), about: ["file"] });
  }
  return createPromptContext(parts, undefined, folders ? { folders } : {});
}

// The inline packet as the message shows it: its `input` named as the message names files (`displayPath`),
// which `cad <type> snapshot --job` reads from the agent's workspace or `~` as it read the absolute path.
function shownPacket(inline, folders) {
  if (!folders) return inline;
  try {
    const packet = JSON.parse(inline);
    if (!packet || typeof packet !== "object" || typeof packet.input !== "string") return inline;
    return JSON.stringify({ ...packet, input: displayPath(packet.input, folders) });
  } catch { return inline; }
}

/**
 * A Quick Edit as the person copies it: its references by their files' paths (from the workspace, else `~/`), and its
 * snapshot as inline JSON or the path it was saved at.
 * @returns {Promise<string>}
 */
export async function copiedQuickEdit(context) {
  return resolvePromptMessage(context);
}
