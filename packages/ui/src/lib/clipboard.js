function getDocumentSelection(doc) {
  if (!doc || typeof doc.getSelection !== "function") {
    return null;
  }
  try {
    return doc.getSelection();
  } catch {
    return null;
  }
}

function preserveSelection(selection) {
  if (!selection || typeof selection.rangeCount !== "number" || typeof selection.getRangeAt !== "function") {
    return [];
  }

  const ranges = [];
  for (let index = 0; index < selection.rangeCount; index += 1) {
    try {
      ranges.push(selection.getRangeAt(index));
    } catch {
      return ranges;
    }
  }
  return ranges;
}

function restoreSelection(selection, ranges) {
  if (!selection || typeof selection.removeAllRanges !== "function" || typeof selection.addRange !== "function") {
    return;
  }
  try {
    selection.removeAllRanges();
    for (const range of ranges) {
      selection.addRange(range);
    }
  } catch {
    // Selection restoration is a courtesy; copying already happened.
  }
}

function focusElement(element) {
  if (!element || typeof element.focus !== "function") {
    return;
  }
  try {
    element.focus({ preventScroll: true });
  } catch {
    try {
      element.focus();
    } catch {
      // Ignore focus restoration failures.
    }
  }
}

function execCommandCopyText(text) {
  const doc = globalThis.document;
  if (!doc?.body || typeof doc.createElement !== "function" || typeof doc.execCommand !== "function") {
    return false;
  }

  const activeElement = doc.activeElement;
  const selection = getDocumentSelection(doc);
  const preservedRanges = preserveSelection(selection);
  const textarea = doc.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.top = "0";
  textarea.style.left = "-9999px";
  textarea.style.width = "1px";
  textarea.style.height = "1px";
  textarea.style.opacity = "0";

  doc.body.appendChild(textarea);
  focusElement(textarea);
  textarea.select();

  let copied = false;
  try {
    copied = doc.execCommand("copy");
  } finally {
    doc.body.removeChild(textarea);
    restoreSelection(selection, preservedRanges);
    if (activeElement && activeElement !== textarea) {
      focusElement(activeElement);
    }
  }

  return copied;
}

function normalizeClipboardImageBlob(blob, fallbackType) {
  if (!blob || typeof blob !== "object") {
    throw new Error("Failed to encode screenshot");
  }

  const type = String(blob.type || fallbackType || "").trim();
  if (!type) {
    return blob;
  }
  if (blob.type === type) {
    return blob;
  }
  return blob.slice(0, blob.size, type);
}

function isClipboardPermissionError(error) {
  const name = String(error?.name || "").toLowerCase();
  const message = String(error?.message || error || "").toLowerCase();
  return (
    name.includes("notallowed") ||
    name.includes("security") ||
    message.includes("permission") ||
    message.includes("denied") ||
    message.includes("not allowed")
  );
}

function blockedClipboardError(error) {
  if (isClipboardPermissionError(error)) {
    return new Error("Clipboard image copy is blocked in this browser.");
  }
  return error instanceof Error ? error : new Error("Clipboard image copy failed");
}

function blockedClipboardTextReadError(error) {
  if (isClipboardPermissionError(error)) {
    return new Error("Clipboard paste is blocked in this browser");
  }
  return error instanceof Error ? error : new Error("Clipboard paste failed");
}

export async function copyImageBlobToClipboard(blobOrPromise, { type = "image/png" } = {}) {
  const clipboard = globalThis.navigator?.clipboard;
  const ClipboardItemCtor = globalThis.ClipboardItem;
  const normalizedType = String(type || "image/png").trim() || "image/png";
  const blobPromise = Promise.resolve(blobOrPromise).then((blob) => normalizeClipboardImageBlob(blob, normalizedType));

  if (!clipboard?.write || typeof ClipboardItemCtor !== "function") {
    throw new Error("Clipboard image copy is not supported in this browser");
  }

  let item;
  try {
    item = new ClipboardItemCtor({ [normalizedType]: blobPromise });
  } catch {
    const blob = await blobPromise;
    const blobType = String(blob.type || normalizedType).trim() || normalizedType;
    item = new ClipboardItemCtor({ [blobType]: blob });
  }

  try {
    await clipboard.write([item]);
  } catch (error) {
    blobPromise.catch(() => {});
    throw blockedClipboardError(error);
  }
  return await blobPromise;
}

export async function copyTextToClipboard(text) {
  const clipboardText = String(text ?? "");
  const clipboard = globalThis.navigator?.clipboard;
  let clipboardError = null;

  if (typeof clipboard?.writeText === "function") {
    try {
      await clipboard.writeText(clipboardText);
      return;
    } catch (error) {
      clipboardError = error;
    }
  }

  if (execCommandCopyText(clipboardText)) {
    return;
  }

  if (clipboardError instanceof Error) {
    throw clipboardError;
  }
  throw new Error("Clipboard is unavailable");
}

export async function readTextFromClipboard() {
  const clipboard = globalThis.navigator?.clipboard;
  if (typeof clipboard?.readText !== "function") {
    throw new Error("Clipboard paste is unavailable");
  }
  try {
    return await clipboard.readText();
  } catch (error) {
    throw blockedClipboardTextReadError(error);
  }
}
