/**
 * `src/renderer/lib/mermaid.ts`: the transcript's Mermaid plugin loads the
 * diagram engine on the first render, not with the window, and a config
 * Streamdown sets before then still reaches it.
 */
import { beforeEach, expect, it, vi } from "vitest";

const loads = vi.hoisted(() => ({ count: 0 }));
const real = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string, source: string) => ({ svg: `<svg id="${id}">${source}</svg>` })),
}));

vi.mock("@streamdown/mermaid", () => {
  loads.count += 1;
  return {
    mermaid: {
      name: "mermaid",
      type: "diagram",
      language: "mermaid",
      getMermaid(config?: object) {
        if (config) real.initialize(config);
        return real;
      },
    },
  };
});

beforeEach(() => {
  real.initialize.mockClear();
  real.render.mockClear();
});

it("does not load the engine until a diagram is drawn", async () => {
  const { mermaid } = await import("@renderer/lib/mermaid");
  const instance = mermaid.getMermaid({ theme: "dark" });
  instance.initialize({ theme: "dark" });
  expect(loads.count).toBe(0);

  await expect(instance.render("d1", "graph TD; A-->B")).resolves.toEqual({ svg: '<svg id="d1">graph TD; A-->B</svg>' });
  expect(loads.count).toBe(1);
  // The config given before the load reached the real instance, once.
  expect(real.initialize).toHaveBeenCalledTimes(1);
  expect(real.initialize).toHaveBeenCalledWith({ theme: "dark" });

  await instance.render("d2", "graph LR; C-->D");
  expect(real.initialize).toHaveBeenCalledTimes(1);
  expect(real.render).toHaveBeenLastCalledWith("d2", "graph LR; C-->D");
});

it("hands a later config over with the next render", async () => {
  const { mermaid } = await import("@renderer/lib/mermaid");
  const instance = mermaid.getMermaid({ theme: "default" });
  await instance.render("d3", "graph TD; E-->F");
  expect(real.initialize).toHaveBeenCalledWith({ theme: "default" });
  expect(mermaid).toMatchObject({ name: "mermaid", type: "diagram", language: "mermaid" });
});

it("retries the import after a failure instead of remembering it", async () => {
  vi.resetModules();
  let attempts = 0;
  vi.doMock("@streamdown/mermaid", () => {
    attempts += 1;
    if (attempts === 1) {
      throw new Error("Failed to fetch dynamically imported module");
    }
    return { mermaid: { name: "mermaid", type: "diagram", language: "mermaid", getMermaid: () => real } };
  });
  const { mermaid } = await import("@renderer/lib/mermaid");
  const instance = mermaid.getMermaid();
  await expect(instance.render("d4", "graph TD; G-->H")).rejects.toThrow();
  await expect(instance.render("d5", "graph TD; I-->J")).resolves.toEqual({ svg: '<svg id="d5">graph TD; I-->J</svg>' });
  expect(attempts).toBe(2);
});
