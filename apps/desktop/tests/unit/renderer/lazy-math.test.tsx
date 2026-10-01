/**
 * `src/renderer/lib/math.ts`: the transcript's math plugin (and KaTeX with it)
 * is imported when a text with a formula is first drawn, never for one
 * without, and the message re-renders with it once it lands.
 */
import { act, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

const loads = vi.hoisted(() => ({ math: 0, css: 0 }));

vi.mock("@streamdown/math", () => {
  loads.math += 1;
  return { math: { name: "katex", type: "math", remarkPlugin: [], rehypePlugin: [], getStyles: () => "" } };
});
vi.mock("katex/dist/katex.min.css", () => {
  loads.css += 1;
  return {};
});

const seen: unknown[] = [];
vi.mock("streamdown", () => ({
  Streamdown: ({ plugins, children }: { plugins: object; children: string }) => {
    seen.push(Object.keys(plugins));
    return <p>{children}</p>;
  },
}));

it("imports the typesetter with the first formula, once, and not for plain markdown", async () => {
  const { MessageResponse } = await import("@renderer/components/ai-elements/message");
  const { hasMath } = await import("@renderer/lib/math");
  expect(hasMath("# a heading with `code` and a $5 price")).toBe(false);
  expect(hasMath("$$x^2$$")).toBe(true);
  expect(hasMath("so $x^2$ holds")).toBe(true);
  expect(hasMath("inline \\(x\\)")).toBe(true);

  const view = render(<MessageResponse>plain **markdown**</MessageResponse>);
  await act(async () => {});
  expect(loads).toEqual({ math: 0, css: 0 });
  expect(seen.at(-1)).not.toContain("math");

  view.rerender(<MessageResponse>{"energy: $$E = mc^2$$"}</MessageResponse>);
  // Drawn without it first, then again with it when the import lands.
  expect(seen.at(-1)).not.toContain("math");
  await act(async () => {});
  expect(loads).toEqual({ math: 1, css: 1 });
  expect(seen.at(-1)).toContain("math");

  view.rerender(<MessageResponse>{"and $$a + b$$"}</MessageResponse>);
  await act(async () => {});
  expect(loads).toEqual({ math: 1, css: 1 });
  expect(seen.at(-1)).toContain("math");

  // A text without math goes back to the short list.
  view.rerender(<MessageResponse>no formulas</MessageResponse>);
  expect(seen.at(-1)).not.toContain("math");
});
