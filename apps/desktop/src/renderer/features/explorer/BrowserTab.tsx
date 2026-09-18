import { ArrowLeft, ArrowRight, Camera, ExternalLink, Globe, MessageSquareQuote, RotateCw, Terminal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  WebPreview,
  WebPreviewNavigation,
  WebPreviewNavigationButton,
} from "@renderer/components/ai-elements/web-preview";
import { Button } from "@renderer/components/ui/button";
import { cn } from "@renderer/lib/utils";
import { useBrowser } from "@renderer/state/browser";

import { EmptyState } from "@hardcore/ui/navigation";
import { createPromptContext } from "@hardcore/core/prompt";
import { createDesktopPromptContext } from "./host/promptContext";

/** Chrome for a main-owned native page. Its document survives this component. */
type ConsoleLine = { level: "log" | "warn" | "error"; message: string };
export function BrowserTab({ projectId, root, tabId, url }: { projectId: string; root: string | null; tabId: string; url: string | null }) {
  const viewRef = useRef<HTMLDivElement | null>(null);
  const target = useBrowser(state => state.targets[tabId]);
  const failure = useBrowser(state => state.errors[tabId]);
  const mount = useBrowser(state => state.mount);
  const navigatePage = useBrowser(state => state.navigate);
  const clearConsole = useBrowser(state => state.clearConsole);
  const contextAttachment = useBrowser(state => state.contextAttachment);
  const prompt = useMemo(() => createDesktopPromptContext(projectId, root, JSON.stringify(["desktop", projectId, root])), [projectId, root]);
  const [adding, setAdding] = useState(false);
  const [promptStatus, setPromptStatus] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ value: string; source: string | null } | null>(null);
  const [showConsole, setShowConsole] = useState(false);
  const current = target?.url && target.url !== "about:blank" ? target.url : url;
  const loading = target?.loading ?? false;
  const canGoBack = target?.canGoBack ?? false;
  const canGoForward = target?.canGoForward ?? false;
  const logs = target?.logs ?? [];
  const initialURL = useRef(url);
  useEffect(() => {
    if (viewRef.current) return mount({ projectId, root, tabId }, initialURL.current, viewRef.current);
  }, [mount, projectId, root, tabId]);
  const address = draft?.source === current ? draft.value : current ?? "";
  const setAddress = (value: string) => setDraft({ value, source: current });
  const navigate = useCallback((raw: string) => {
    const resolved = resolveAddress(raw);
    if (!resolved) return;
    setDraft({ value: resolved, source: current });
    void navigatePage({ projectId, root, tabId }, { url: resolved });
  }, [navigatePage, projectId, root, tabId, current]);
  const move = (direction: "back" | "forward" | "reload" | "stop") => void navigatePage({ projectId, root, tabId }, { direction });

  const addContext = (kind: "selection" | "screenshot") => {
    if (!target || !current || adding) return;
    setAdding(true); setPromptStatus(null);
    const referenceId = crypto.randomUUID();
    // Deliver immediately: the draft destination binds before native capture finishes.
    const context = createPromptContext([
      { id: referenceId, kind: "reference", reference: { resource: { kind: "url", url: target.url, revision: String(target.generation) }, target: { kind: "whole-resource" }, label: target.title || target.url } },
      { id: crypto.randomUUID(), kind: "attachment", name: kind === "screenshot" ? "browser-page.png" : "browser-selection.txt", mimeType: kind === "screenshot" ? "image/png" : "text/plain", about: [referenceId], content: contextAttachment({ projectId, root, tabId }, target, kind) },
    ]);
    void prompt.deliver(context).then(result => {
      setPromptStatus(result.status === "added" ? "Added to prompt" : ("message" in result ? result.message : undefined) ?? "Could not add browser context.");
    }).catch(error => setPromptStatus(error instanceof Error ? error.message : String(error))).finally(() => setAdding(false));
  };

  const errors = logs.filter((line) => line.level === "error").length;

  return (
    <WebPreview className="size-full rounded-none border-0 bg-transparent">
      <WebPreviewNavigation className="h-9 gap-0.5 px-2 py-0">
        <WebPreviewNavigationButton
          disabled={!canGoBack}
          onClick={() => move("back")}
          tooltip="Back"
        >
          <ArrowLeft className="size-3.5" />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton
          disabled={!canGoForward}
          onClick={() => move("forward")}
          tooltip="Forward"
        >
          <ArrowRight className="size-3.5" />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton
          disabled={!current}
          onClick={() => move(loading ? "stop" : "reload")}
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

        <WebPreviewNavigationButton disabled={!current || !target || adding} onClick={() => addContext("selection")} aria-label="Add selected text to prompt" tooltip="Add selected text to prompt">
          <MessageSquareQuote className="size-3.5" />
        </WebPreviewNavigationButton>
        <WebPreviewNavigationButton disabled={!current || !target || adding} onClick={() => addContext("screenshot")} aria-label="Add page screenshot to prompt" tooltip="Add page screenshot to prompt">
          <Camera className="size-3.5" />
        </WebPreviewNavigationButton>
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

      {promptStatus ? <p className="px-3 py-1 text-xs text-muted-foreground" role="status">{promptStatus}</p> : null}
      {failure ? <p className="px-3 py-1 text-xs text-destructive" role="alert">{failure}</p> : null}
      <div className="relative min-h-0 flex-1 overflow-hidden border-t bg-background" data-browser-target={tabId} ref={viewRef}>
        {!current ? (
          <EmptyState description="Type a URL or a search above. Agents can open pages here too." icon={Globe} title="Start browsing" />
        ) : null}
      </div>

      {showConsole ? (
        <ConsolePanel logs={logs} onClear={() => clearConsole(tabId)} />
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
