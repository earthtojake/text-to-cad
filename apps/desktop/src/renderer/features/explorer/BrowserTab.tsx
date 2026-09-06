import { ArrowLeft, ArrowRight, ExternalLink, Globe, RotateCw, Terminal } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  WebPreview,
  WebPreviewNavigation,
  WebPreviewNavigationButton,
} from "@renderer/components/ai-elements/web-preview";
import { Button } from "@renderer/components/ui/button";
import { cn } from "@renderer/lib/utils";
import { useExplorer } from "@renderer/state/explorer";

import { EmptyState } from "./EmptyState";

/**
 * A browser, as a tab in the one strip.
 *
 * An Electron `<webview>`, not an `<iframe>`: a webview is its own process
 * with its own session, it is not stopped by `X-Frame-Options` (which every
 * site worth opening sets), and it can be asked for its navigation state. An
 * iframe would be a pane that shows a blank page for most of the web.
 *
 * The chrome is AI Elements' Web Preview — its navigation row, its address
 * field and its console panel — with the body replaced, since `WebPreviewBody`
 * renders the iframe this tab cannot use.
 *
 * The URL is persisted on the tab, so a reopened strip comes back where it was.
 */

/** Chromium's own tag; React has no JSX typing for it. */
type WebviewElement = HTMLElement & {
  src: string;
  canGoBack(): boolean;
  canGoForward(): boolean;
  goBack(): void;
  goForward(): void;
  reload(): void;
  stop(): void;
  getURL(): string;
};

type ConsoleLine = { level: "log" | "warn" | "error"; message: string; timestamp: Date };

export function BrowserTab({ tabId, url }: { tabId: string; url: string | null }) {
  const update = useExplorer((state) => state.update);
  const viewRef = useRef<WebviewElement | null>(null);

  const [address, setAddress] = useState(url ?? "");
  const [current, setCurrent] = useState(url);
  const [loading, setLoading] = useState(false);
  const [canGoBack, setCanGoBack] = useState(false);
  const [canGoForward, setCanGoForward] = useState(false);
  const [logs, setLogs] = useState<ConsoleLine[]>([]);
  const [showConsole, setShowConsole] = useState(false);

  const navigate = useCallback(
    (raw: string) => {
      const resolved = resolveAddress(raw);
      if (!resolved) {
        return;
      }
      setCurrent(resolved);
      setAddress(resolved);
      setLogs([]);
      update(tabId, { url: resolved });
    },
    [tabId, update],
  );

  // The webview's events are DOM events on the tag, so they are attached
  // imperatively rather than as React props.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) {
      return;
    }
    const sync = () => {
      setCanGoBack(view.canGoBack());
      setCanGoForward(view.canGoForward());
    };
    const onStart = () => {
      setLoading(true);
    };
    const onStop = () => {
      setLoading(false);
      sync();
      // A redirect or a link click changes the address without going through
      // `navigate`, and the bar has to follow it.
      const at = view.getURL();
      if (at && at !== "about:blank") {
        setAddress(at);
        update(tabId, { url: at });
      }
    };
    const onConsole = (event: Event) => {
      const detail = event as Event & { level: number; message: string };
      setLogs((previous) =>
        [
          ...previous,
          {
            // Chromium's levels: 0 verbose, 1 info, 2 warning, 3 error.
            level: detail.level >= 3 ? "error" : detail.level === 2 ? "warn" : "log",
            message: detail.message,
            timestamp: new Date(),
          } as ConsoleLine,
        ].slice(-200),
      );
    };

    view.addEventListener("did-start-loading", onStart);
    view.addEventListener("did-stop-loading", onStop);
    view.addEventListener("did-navigate", onStop);
    view.addEventListener("did-navigate-in-page", onStop);
    view.addEventListener("console-message", onConsole);
    return () => {
      view.removeEventListener("did-start-loading", onStart);
      view.removeEventListener("did-stop-loading", onStop);
      view.removeEventListener("did-navigate", onStop);
      view.removeEventListener("did-navigate-in-page", onStop);
      view.removeEventListener("console-message", onConsole);
    };
  }, [current, tabId, update]);

  const errors = logs.filter((line) => line.level === "error").length;

  return (
    <WebPreview className="size-full rounded-none border-0 bg-transparent">
      <WebPreviewNavigation className="h-9 gap-0.5 px-2 py-0">
        <WebPreviewNavigationButton
          disabled={!canGoBack}
          onClick={() => viewRef.current?.goBack()}
          tooltip="Back"
        >
          <ArrowLeft className="size-3.5" />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton
          disabled={!canGoForward}
          onClick={() => viewRef.current?.goForward()}
          tooltip="Forward"
        >
          <ArrowRight className="size-3.5" />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton
          disabled={!current}
          onClick={() => (loading ? viewRef.current?.stop() : viewRef.current?.reload())}
          tooltip={loading ? "Stop" : "Reload"}
        >
          <RotateCw className={cn("size-3.5", loading && "animate-spin")} />
        </WebPreviewNavigationButton>

        <input
          aria-label="Address"
          className="mx-1 h-6 min-w-0 flex-1 rounded-md bg-muted/60 px-2.5 text-[12px] outline-none placeholder:text-muted-foreground focus:bg-muted"
          onChange={(event) => setAddress(event.target.value)}
          onFocus={(event) => event.currentTarget.select()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              navigate(event.currentTarget.value);
            }
            if (event.key === "Escape") {
              setAddress(current ?? "");
              event.currentTarget.blur();
            }
          }}
          placeholder="Search or enter a URL"
          spellCheck={false}
          value={address}
        />

        <WebPreviewNavigationButton
          onClick={() => setShowConsole((open) => !open)}
          tooltip={errors > 0 ? `Console (${errors} errors)` : "Console"}
        >
          <Terminal className={cn("size-3.5", errors > 0 && "text-destructive")} />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton
          disabled={!current}
          onClick={() => {
            if (current) {
              void window.hardcore.shell.openExternal({ url: current }).catch(() => {});
            }
          }}
          tooltip="Open in your browser"
        >
          <ExternalLink className="size-3.5" />
        </WebPreviewNavigationButton>
      </WebPreviewNavigation>

      <div className="relative min-h-0 flex-1 overflow-hidden border-t bg-background">
        {current ? (
          <webview
            // Remounting on a URL change is what makes `src` behave: the tag
            // reads it once, and assigning it later navigates only sometimes.
            key={current}
            // `@types/react`'s `HTMLWebViewElement` is an empty interface — it
            // knows the tag exists and nothing about Electron's methods on it,
            // so the ref is typed to what this component actually calls.
            ref={viewRef as unknown as React.Ref<HTMLElement>}
            src={current}
            // Pinned, not `width: 100%`: the tag sizes itself from the guest
            // page's own layout, so a page wider than the pane paints past
            // the window edge unless it is given an explicit box.
            style={{ position: "absolute", inset: 0, display: "flex" }}
          />
        ) : (
          <EmptyState
            description="Type a URL or a search above. Agents can open pages here too."
            icon={Globe}
            title="Start browsing"
          />
        )}
      </div>

      {showConsole ? (
        <ConsolePanel logs={logs} onClear={() => setLogs([])} />
      ) : null}
    </WebPreview>
  );
}

/**
 * The console.
 *
 * AI Elements' `WebPreviewConsole` is a `Collapsible` whose open state lives in
 * the Web Preview context, which is not the state this tab keeps (the toggle is
 * in the navigation row, beside the other buttons). So the panel is rendered
 * conditionally and the component is used for its styling, always open.
 */
function ConsolePanel({ logs, onClear }: { logs: ConsoleLine[]; onClear: () => void }) {
  return (
    <div className="shrink-0 border-t bg-muted/40">
      <div className="flex h-7 items-center justify-between px-3">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Console
        </span>
        <Button className="h-5 px-1.5 text-[11px]" onClick={onClear} size="sm" variant="ghost">
          Clear
        </Button>
      </div>
      <div className="max-h-40 overflow-auto px-3 pb-2 font-mono text-[11px]" data-selectable>
        {logs.length === 0 ? (
          <p className="py-2 text-muted-foreground">No console output</p>
        ) : (
          logs.map((line, index) => (
            <p
              className={cn(
                "py-px break-all",
                line.level === "error" && "text-destructive",
                line.level === "warn" && "text-amber-600 dark:text-amber-400",
              )}
              key={index}
            >
              {line.message}
            </p>
          ))
        )}
      </div>
    </div>
  );
}

/** Kept out of the component so it can be reasoned about (and tested) alone. */
export function resolveAddress(raw: string): string | null {
  const value = raw.trim();
  if (value === "") {
    return null;
  }
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
    return value;
  }
  // `localhost:5273`, `example.com`, `192.168.0.4/status` — an address, not a
  // search. A bare word with no dot and no port is a search.
  if (/^localhost(:\d+)?(\/|$)/i.test(value) || /^[\w-]+(\.[\w-]+)+(:\d+)?(\/|$)/.test(value)) {
    return `https://${value}`.replace(/^https:\/\/localhost/, "http://localhost");
  }
  return `https://duckduckgo.com/?q=${encodeURIComponent(value)}`;
}
