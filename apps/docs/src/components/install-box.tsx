"use client";

import { useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import { CopyButton } from "@/components/copy-button";
import { installCommands } from "@/lib/content";
import { cn } from "@/lib/utils";

// The toggle's short name for each system in `installCommands`.
function shortLabel(system: string) {
  return system.startsWith("Windows") ? "Windows" : "macOS / Linux";
}

const WINDOWS = Math.max(
  installCommands.findIndex(({ system }) => system.startsWith("Windows")),
  0
);

// Whether the browser runs on Windows: false on the server and while hydrating, then the browser's
// answer, which never changes.
const subscribeToNothing = () => () => {};
const browserIsWindows = () => navigator.userAgent.includes("Windows");
const serverIsWindows = () => false;

// Letter-spaced a little less on a phone, so the label and the toggle share a row at 375px; narrower,
// the toggle wraps under the label.
const LABEL_CLASS =
  "text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground sm:tracking-[0.14em]";

/** The hero's one-line install: a toggle between the systems (macOS / Linux, Windows) and the chosen
 * one's command with its Copy. The server renders macOS / Linux; a Windows browser switches to
 * Windows once the page has loaded. */
export function InstallBox() {
  const isWindows = useSyncExternalStore(subscribeToNothing, browserIsWindows, serverIsWindows);
  // The system the visitor picked, or none yet: then the one their browser runs on.
  const [chosen, setActive] = useState<number | null>(null);
  const active = chosen ?? (isWindows ? WINDOWS : 0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  const select = (index: number) => {
    setActive(index);
    tabs.current[index]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const last = installCommands.length - 1;
    const next =
      event.key === "ArrowRight" ? (active === last ? 0 : active + 1)
      : event.key === "ArrowLeft" ? (active === 0 ? last : active - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    select(next);
  };

  const { system, language, command } = installCommands[active];

  return (
    <div className="w-full max-w-[660px] rounded-xl border border-border bg-card text-left shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-2 px-4 pt-3 pb-2 sm:gap-x-3">
        <span id="one-line-install" className={LABEL_CLASS}>
          ONE-LINE INSTALL
        </span>
        <div role="tablist" aria-labelledby="one-line-install" className="flex rounded-full bg-muted p-0.5">
          {installCommands.map((entry, index) => {
            const selected = index === active;
            return (
              <button
                key={entry.system}
                ref={(element) => {
                  tabs.current[index] = element;
                }}
                type="button"
                role="tab"
                id={`install-tab-${index}`}
                aria-selected={selected}
                aria-controls="install-command"
                tabIndex={selected ? 0 : -1}
                onClick={() => setActive(index)}
                onKeyDown={onKeyDown}
                className={cn(
                  "h-7 cursor-pointer rounded-full px-2.5 text-xs font-medium whitespace-nowrap transition outline-none sm:px-3 focus-visible:ring-3 focus-visible:ring-ring/50",
                  selected
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {shortLabel(entry.system)}
              </button>
            );
          })}
        </div>
      </div>
      <div
        id="install-command"
        role="tabpanel"
        aria-labelledby={`install-tab-${active}`}
        className="flex min-w-0 items-center gap-3 px-4 pb-3"
      >
        <span className="shrink-0 select-none font-mono text-sm text-muted-foreground" aria-hidden="true">
          {language === "powershell" ? ">" : "$"}
        </span>
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-pre font-mono text-sm text-foreground">
          {command}
        </code>
        <CopyButton text={command} label={`Copy the install command for ${system}`} />
      </div>
    </div>
  );
}
