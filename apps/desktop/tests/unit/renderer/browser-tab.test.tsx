/** BrowserTab's address bar and navigation row, against a mounted-but-empty native page. */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BrowserTab } from "@renderer/features/explorer/BrowserTab";
import { useBrowser } from "@renderer/state/browser";
import type { BrowserTarget } from "@shared/browser";

const target: BrowserTarget = { sessionId: "first", tabId: "page", projectId: "project", root: "/project", generation: 1, title: "Example page", url: "https://example.com/", loading: false, visible: true, canGoBack: true, canGoForward: true, logs: [] };
const navigate = vi.fn();
const originalMount = useBrowser.getState().mount;
const originalNavigate = useBrowser.getState().navigate;
beforeEach(() => {
  navigate.mockReset().mockResolvedValue(undefined);
  useBrowser.setState({ targets: { page: target }, errors: {}, consoles: {}, mount: () => () => {}, navigate });
});
afterEach(() => { cleanup(); useBrowser.setState({ mount: originalMount, navigate: originalNavigate }); });
const renderTab = () => render(<BrowserTab sessionId="first" projectId="project" root={null} tabId="page" url={target.url} />);

it("names its icon-only buttons, and says whether the console is open", () => {
  renderTab();
  for (const name of [/^back$/i, /^forward$/i, /^reload$/i, /open in your browser/i]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
  const console = screen.getByRole("button", { name: /^console$/i });
  expect(console).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(console);
  expect(screen.getByRole("button", { name: /^console$/i })).toHaveAttribute("aria-pressed", "true");
});

it("does not navigate on the Enter that commits an IME composition", () => {
  renderTab();
  const input = screen.getByRole("textbox", { name: "Address" });
  fireEvent.change(input, { target: { value: "example.org" } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  expect(navigate).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(navigate).toHaveBeenCalledWith(expect.anything(), { url: "https://example.org" });
});

it("keeps a half-typed address when the page's URL changes under it, and resyncs once focus leaves", () => {
  renderTab();
  const input = screen.getByRole("textbox", { name: "Address" });
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "exam" } });
  // A pushState, redirect or agent navigation while the person types.
  act(() => useBrowser.setState({ targets: { page: { ...target, url: "https://example.com/next" } } }));
  expect(input).toHaveValue("exam");
  fireEvent.blur(input);
  expect(input).toHaveValue("https://example.com/next");
});

it("keeps a half-typed address across blur", () => {
  renderTab();
  const input = screen.getByRole("textbox", { name: "Address" });
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "exam" } });
  fireEvent.blur(input);
  expect(input).toHaveValue("exam");
});

it("drops a half-typed address on Escape, so the page's next URL shows", () => {
  renderTab();
  const input = screen.getByRole("textbox", { name: "Address" });
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "exam" } });
  fireEvent.keyDown(input, { key: "Escape" });
  fireEvent.blur(input);
  expect(input).toHaveValue("https://example.com/");
  act(() => useBrowser.setState({ targets: { page: { ...target, url: "https://example.com/next" } } }));
  expect(input).toHaveValue("https://example.com/next");
});
