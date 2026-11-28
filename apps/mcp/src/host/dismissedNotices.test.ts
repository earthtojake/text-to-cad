import { describe, expect, it } from "vitest";
import { dismissNotice, dismissedNotices } from "./dismissedNotices.js";

/** A frame's local storage, as every view of it sees it. */
function frameStorage() {
  const kept = new Map<string, string>();
  return { kept, getItem: (key: string) => kept.get(key) ?? null, setItem: (key: string, value: string) => { kept.set(key, String(value)); } };
}

describe("the notices dismissed in the CAD app", () => {
  it("keeps each by its id, once, for every view of the frame", () => {
    const storage = frameStorage();
    expect(dismissedNotices(storage)).toEqual([]);
    dismissNotice("install-moved", storage);
    dismissNotice("plain", storage);
    dismissNotice("install-moved", storage);
    expect(dismissedNotices(storage)).toEqual(["install-moved", "plain"]);
  });

  it("reads none and keeps none where the frame's storage refuses or holds something else, and never fails", () => {
    const refused = () => { throw new DOMException("denied", "SecurityError"); };
    const storage = { getItem: refused, setItem: refused };
    expect(() => dismissNotice("install-moved", storage)).not.toThrow();
    expect(dismissedNotices(storage)).toEqual([]);
    for (const held of ["not json", '{"a":1}', '[1,"a",null]']) {
      const other = frameStorage();
      other.setItem("text-to-cad.notices.dismissed", held);
      expect(dismissedNotices(other)).toEqual(held.startsWith("[") ? ["a"] : []);
    }
  });
});
