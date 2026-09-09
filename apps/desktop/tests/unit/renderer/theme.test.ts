/**
 * The colour scheme: the default, how `system` resolves, and the two things
 * that keep the window from flashing the wrong one.
 *
 * The bug this covers: settings live in main's sqlite, so the theme could only
 * be applied from React's first passive effect — one paint after the window
 * was shown. Every launch, reload and dev-server hot reload started light
 * whatever the person had chosen, then flipped. The cache read before render
 * is the fix, and it is only as good as the write that keeps it current.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

// The two files that carry the pre-paint half of this, as bytes, through
// Vite's `?raw` — the same way the markdown tests read the repository's own
// documents. A copy of either written for this test would be a copy written to
// pass it.
import themeScript from "@renderer/public/theme.js?raw";
import indexHtml from "@renderer/index.html?raw";

import {
  applyCachedTheme,
  applyResolvedTheme,
  readCachedThemePreference,
  resolveThemePreference,
  useApplyTheme,
  useResolvedTheme,
} from "@renderer/hooks/use-theme";
import { useSettings } from "@renderer/state/settings";
import { defaultSettings } from "@shared/types";

const CACHE_KEY = "hardcore.theme";

/** `prefers-color-scheme: dark`, and a way to move it. */
function stubMatchMedia(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  let matches = prefersDark;
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      get matches() {
        return query.includes("dark") ? matches : false;
      },
      media: query,
      onchange: null,
      addEventListener: (_name: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_name: string, listener: () => void) => listeners.delete(listener),
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  return {
    set(next: boolean) {
      matches = next;
      for (const listener of listeners) {
        listener();
      }
    },
  };
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = "";
  document.documentElement.style.colorScheme = "";
  useSettings.setState({ settings: null, ready: false });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the default", () => {
  it("is System, and System is the OS's answer", () => {
    expect(defaultSettings().theme).toBe("system");
    expect(resolveThemePreference("system", true)).toBe("dark");
    expect(resolveThemePreference("system", false)).toBe("light");
    // A chosen theme is detached from the OS in both directions.
    expect(resolveThemePreference("dark", false)).toBe("dark");
    expect(resolveThemePreference("light", true)).toBe("light");
  });
});

describe("the cache read before render", () => {
  it("is System when there is nothing stored, or something that is not a theme", () => {
    expect(readCachedThemePreference()).toBe("system");
    window.localStorage.setItem(CACHE_KEY, "cinematic");
    expect(readCachedThemePreference()).toBe("system");
    window.localStorage.setItem(CACHE_KEY, "");
    expect(readCachedThemePreference()).toBe("system");
  });

  it("is the stored preference when it is one", () => {
    for (const preference of ["system", "light", "dark"] as const) {
      window.localStorage.setItem(CACHE_KEY, preference);
      expect(readCachedThemePreference()).toBe(preference);
    }
  });

  it("applies dark before render on an OS in dark with no preference stored", () => {
    stubMatchMedia(true);
    applyCachedTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("applies a stored Light even on an OS in dark", () => {
    stubMatchMedia(true);
    window.localStorage.setItem(CACHE_KEY, "light");
    applyCachedTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("survives storage being unavailable", () => {
    stubMatchMedia(true);
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(readCachedThemePreference()).toBe("system");
    expect(() => applyCachedTheme()).not.toThrow();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

describe("applyResolvedTheme", () => {
  it("writes the class Tailwind compiles against and the property the native controls read", () => {
    applyResolvedTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
    applyResolvedTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });
});

describe("useApplyTheme", () => {
  it("holds dark through the gap before the settings read lands, on an OS in dark", () => {
    stubMatchMedia(true);
    applyCachedTheme();
    renderHook(() => useApplyTheme());
    // `settings` is still null here: the fallback is the cache, not `system`
    // with a light OS, and certainly not a repaint to light.
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    act(() => {
      useSettings.setState({ settings: defaultSettings(), ready: true });
    });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("does not repaint to dark for a person on Light while the read is in flight", () => {
    stubMatchMedia(true);
    window.localStorage.setItem(CACHE_KEY, "light");
    applyCachedTheme();
    renderHook(() => useApplyTheme());
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    act(() => {
      useSettings.setState({ settings: { ...defaultSettings(), theme: "light" }, ready: true });
    });
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("follows the OS live while the preference is System", () => {
    const media = stubMatchMedia(false);
    renderHook(() => useApplyTheme());
    act(() => {
      useSettings.setState({ settings: defaultSettings(), ready: true });
    });
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    act(() => media.set(true));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");

    act(() => media.set(false));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("ignores the OS while the preference is a chosen one", () => {
    const media = stubMatchMedia(false);
    renderHook(() => useApplyTheme());
    act(() => {
      useSettings.setState({ settings: { ...defaultSettings(), theme: "dark" }, ready: true });
    });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    act(() => media.set(true));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("writes the cache the next load reads, and only from what main stored", () => {
    stubMatchMedia(true);
    renderHook(() => useApplyTheme());
    // Nothing yet: mirroring the fallback would write the cache over itself.
    expect(window.localStorage.getItem(CACHE_KEY)).toBe(null);

    act(() => {
      useSettings.setState({ settings: { ...defaultSettings(), theme: "light" }, ready: true });
    });
    expect(window.localStorage.getItem(CACHE_KEY)).toBe("light");

    // ...and back to System, so a person who returns to it is not stuck with
    // a stale Light on the next launch.
    act(() => {
      useSettings.setState({ settings: defaultSettings(), ready: true });
    });
    expect(window.localStorage.getItem(CACHE_KEY)).toBe("system");
  });
});

/**
 * `public/theme.js` is the same write, done a few milliseconds earlier by a
 * classic script that cannot import anything. It is a copy by necessity, so
 * the copy is pinned: the key it reads, the ids it accepts, and the two
 * properties it writes.
 */
describe("the pre-paint script", () => {
  const source = themeScript;

  it("is a classic script the html loads first, before the module that boots React", () => {
    const html = indexHtml;
    expect(html).toContain('<script src="./theme.js"></script>');
    // Before `main.tsx`, and in the head — a deferred module runs too late.
    expect(html.indexOf("theme.js")).toBeLessThan(html.indexOf("main.tsx"));
    expect(html.indexOf("theme.js")).toBeLessThan(html.indexOf("</head>"));
    expect(source, "a classic script has no module graph").not.toMatch(/^\s*(import|export)\s/m);
  });

  it("reads the same cache key the module writes", () => {
    window.localStorage.setItem(CACHE_KEY, "dark");
    expect(readCachedThemePreference()).toBe("dark");
    expect(source).toContain(`"${CACHE_KEY}"`);
  });

  it("accepts the same three preferences and no others", () => {
    for (const preference of ["system", "light", "dark"]) {
      expect(source).toContain(`"${preference}"`);
    }
    expect(source).toContain("(prefers-color-scheme: dark)");
  });

  it("makes the same two writes", () => {
    expect(source).toContain('root.classList.toggle("dark", resolved === "dark")');
    expect(source).toContain("root.style.colorScheme = resolved");
  });
});

describe("useResolvedTheme", () => {
  it("is what the embedded CAD surface is handed: light or dark, never system", () => {
    stubMatchMedia(true);
    const { result } = renderHook(() => useResolvedTheme());
    act(() => {
      useSettings.setState({ settings: defaultSettings(), ready: true });
    });
    expect(result.current).toBe("dark");
    act(() => {
      useSettings.setState({ settings: { ...defaultSettings(), theme: "light" }, ready: true });
    });
    expect(result.current).toBe("light");
  });
});
