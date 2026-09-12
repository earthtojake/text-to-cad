import assert from "node:assert/strict";
import test from "node:test";

import { copyImageBlobToClipboard, copyTextToClipboard, readTextFromClipboard } from "./clipboard.js";

function replaceGlobal(name, value) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value
  });
  return () => {
    if (descriptor) {
      Object.defineProperty(globalThis, name, descriptor);
      return;
    }
    delete globalThis[name];
  };
}

function createClipboardDocument({ copyResult = true } = {}) {
  const appended = [];
  const commands = [];
  const restoredRanges = [];
  let textarea = null;
  const activeElement = {
    focusCalls: 0,
    focus() {
      this.focusCalls += 1;
    }
  };
  const selectionRange = { id: "existing-selection" };

  const document = {
    activeElement,
    body: {
      appendChild(element) {
        appended.push(element);
      },
      removeChild(element) {
        const index = appended.indexOf(element);
        if (index >= 0) {
          appended.splice(index, 1);
        }
      }
    },
    createElement(tagName) {
      assert.equal(tagName, "textarea");
      textarea = {
        value: "",
        attributes: new Map(),
        selected: false,
        focused: false,
        style: {},
        setAttribute(name, value) {
          this.attributes.set(name, String(value));
        },
        focus() {
          this.focused = true;
        },
        select() {
          this.selected = true;
        }
      };
      return textarea;
    },
    execCommand(command) {
      commands.push(command);
      return copyResult;
    },
    getSelection() {
      return {
        rangeCount: 1,
        getRangeAt(index) {
          assert.equal(index, 0);
          return selectionRange;
        },
        removeAllRanges() {
          restoredRanges.length = 0;
        },
        addRange(range) {
          restoredRanges.push(range);
        }
      };
    }
  };

  return {
    document,
    get appendedCount() {
      return appended.length;
    },
    get commands() {
      return [...commands];
    },
    get restoredRanges() {
      return [...restoredRanges];
    },
    get textarea() {
      return textarea;
    },
    activeElement
  };
}

test("copyTextToClipboard uses async clipboard when available", async () => {
  const writes = [];
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async writeText(text) {
        writes.push(text);
      }
    }
  });
  const fakeDocument = createClipboardDocument();
  const restoreDocument = replaceGlobal("document", fakeDocument.document);

  try {
    await copyTextToClipboard("hello cad");
  } finally {
    restoreDocument();
    restoreNavigator();
  }

  assert.deepEqual(writes, ["hello cad"]);
  assert.deepEqual(fakeDocument.commands, []);
});

test("copyTextToClipboard falls back to execCommand when async clipboard rejects", async () => {
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async writeText() {
        throw new Error("NotAllowedError");
      }
    }
  });
  const fakeDocument = createClipboardDocument();
  const restoreDocument = replaceGlobal("document", fakeDocument.document);

  try {
    await copyTextToClipboard("#f1");
  } finally {
    restoreDocument();
    restoreNavigator();
  }

  assert.deepEqual(fakeDocument.commands, ["copy"]);
  assert.equal(fakeDocument.appendedCount, 0);
  assert.equal(fakeDocument.textarea.value, "#f1");
  assert.equal(fakeDocument.textarea.selected, true);
  assert.deepEqual(fakeDocument.restoredRanges, [{ id: "existing-selection" }]);
  assert.equal(fakeDocument.activeElement.focusCalls, 1);
});

test("copyTextToClipboard reports unavailable clipboard when every strategy fails", async () => {
  const restoreNavigator = replaceGlobal("navigator", {});
  const fakeDocument = createClipboardDocument({ copyResult: false });
  const restoreDocument = replaceGlobal("document", fakeDocument.document);

  try {
    await assert.rejects(
      copyTextToClipboard("nope"),
      /Clipboard is unavailable/
    );
  } finally {
    restoreDocument();
    restoreNavigator();
  }

  assert.deepEqual(fakeDocument.commands, ["copy"]);
  assert.equal(fakeDocument.appendedCount, 0);
});

test("readTextFromClipboard reads async clipboard text", async () => {
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async readText() {
        return '{"frame": 12.5}';
      }
    }
  });

  try {
    assert.equal(await readTextFromClipboard(), '{"frame": 12.5}');
  } finally {
    restoreNavigator();
  }
});

test("readTextFromClipboard reports blocked paste permissions", async () => {
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async readText() {
        const error = new Error("Permission denied");
        error.name = "NotAllowedError";
        throw error;
      }
    }
  });

  try {
    await assert.rejects(
      readTextFromClipboard(),
      /Clipboard paste is blocked/
    );
  } finally {
    restoreNavigator();
  }
});

test("copyImageBlobToClipboard starts clipboard write before screenshot blob resolves", async () => {
  const events = [];
  let resolveBlob;
  class FakeClipboardItem {
    constructor(items) {
      events.push("item");
      this.items = items;
    }
  }
  const restoreClipboardItem = replaceGlobal("ClipboardItem", FakeClipboardItem);
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async write(items) {
        events.push("write");
        assert.equal(items.length, 1);
        const item = items[0];
        const pngBlobPromise = item.items["image/png"];
        assert.equal(typeof pngBlobPromise?.then, "function");
        const blob = await pngBlobPromise;
        events.push(`resolved:${blob.type}`);
      }
    }
  });
  const blobPromise = new Promise((resolve) => {
    resolveBlob = resolve;
  });

  let copied;
  try {
    copied = copyImageBlobToClipboard(blobPromise);
    assert.deepEqual(events, ["item", "write"]);
    resolveBlob(new Blob(["png"], { type: "image/png" }));
    const result = await copied;
    assert.equal(result.type, "image/png");
  } finally {
    restoreNavigator();
    restoreClipboardItem();
  }

  assert.deepEqual(events, ["item", "write", "resolved:image/png"]);
});

test("copyImageBlobToClipboard rejects when async image clipboard is denied", async () => {
  const events = [];
  class FakeClipboardItem {
    constructor(items) {
      events.push("item");
      this.items = items;
    }
  }
  const restoreClipboardItem = replaceGlobal("ClipboardItem", FakeClipboardItem);
  const restoreNavigator = replaceGlobal("navigator", {
    clipboard: {
      async write() {
        events.push("write");
        throw new Error("Write permission denied.");
      }
    }
  });

  try {
    await assert.rejects(
      copyImageBlobToClipboard(new Blob(["png"], { type: "image/png" })),
      /Clipboard image copy is blocked in this browser/
    );
  } finally {
    restoreNavigator();
    restoreClipboardItem();
  }

  assert.deepEqual(events, ["item", "write"]);
});

test("copyImageBlobToClipboard reports unsupported image clipboard", async () => {
  const restoreClipboardItem = replaceGlobal("ClipboardItem", class {});
  const restoreNavigator = replaceGlobal("navigator", {});

  try {
    await assert.rejects(
      copyImageBlobToClipboard(Promise.resolve(new Blob(["png"], { type: "image/png" }))),
      /Clipboard image copy is not supported/
    );
  } finally {
    restoreNavigator();
    restoreClipboardItem();
  }
});
