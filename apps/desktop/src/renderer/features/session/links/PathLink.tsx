import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Box, FileText, Folder } from "lucide-react";
import { createContext, useContext, useEffect, type AnchorHTMLAttributes, type ReactNode } from "react";

import { cn } from "@renderer/lib/utils";
import { useExplorer } from "@renderer/state/explorer";
import { usePathKind, usePathLinks } from "@renderer/state/path-links";
import { isCadFile, isSelectorList } from "@shared/cad-refs";
import type { ExplorerRoot } from "@shared/types";

/**
 * The project and root a transcript's paths are relative to — the session's
 * worktree when it runs in one (plan §9), else the project. Provided by
 * `SessionView` around the transcript; without it a path is prose.
 */
export type TranscriptScope = { projectId: string; root: ExplorerRoot };

export const TranscriptScopeContext = createContext<TranscriptScope | null>(null);

/** What a link's href names, when it names a path: the file half and the selector half. */
export type PathTarget = { path: string; selector: string };

/**
 * A path out of a markdown link's href, or null for a URL.
 *
 * `remarkPathLinks` writes `./models/x.step#o1`; rehype-harden rewrites a
 * path-relative URL to `/models/x.step#o1` (and percent-encodes it); an
 * agent that wrote `[the part](models/x.step)` by hand arrives as that. All
 * three are the same file, and a leading `/` here is not an absolute path
 * on the machine — every path in a transcript is relative to the scope.
 */
export function pathTarget(href: string | undefined): PathTarget | null {
  if (!href || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("//")) {
    return null;
  }
  const hash = href.indexOf("#");
  const rawPath = hash >= 0 ? href.slice(0, hash) : href;
  const rawSelector = hash >= 0 ? href.slice(hash + 1) : "";
  let path: string;
  let selector: string;
  try {
    path = decodeURIComponent(rawPath);
    selector = decodeURIComponent(rawSelector);
  } catch {
    return null;
  }
  path = path.replace(/^(\.\/|\/)+/, "").replace(/\/+$/, "");
  // A `..` segment climbs out; `v1..v2.txt` and `..keep/a.txt` are only names.
  if (!path || path.split(/[\\/]/).includes("..")) {
    return null;
  }
  return { path, selector: selector && isSelectorList(selector) ? selector : "" };
}

/**
 * The transcript's `a`: a path that exists opens in the explorer, a path
 * that does not is the words it was, and a URL is a link to the outside.
 */
export function PathLink({
  href,
  children,
  className,
  node: _node,
  // A markdown link's own title would be a native one; the hint says it all.
  title: _title,
  ...rest
}: AnchorHTMLAttributes<HTMLAnchorElement> & { node?: unknown; children?: ReactNode }) {
  const scope = useContext(TranscriptScopeContext);
  const target = pathTarget(href);
  if (!target || !scope) {
    if (!href || !/^https?:/i.test(href)) {
      return <span className={className}>{children}</span>;
    }
    // `target="_blank"` reaches main's window-open handler, which hands the
    // URL to the OS browser rather than opening a window of its own. The
    // label is the agent's words and one click opens it, so the hint says
    // where it really goes — broken anywhere, since a URL has no spaces to
    // wrap at and a long one ran out of the hint's box.
    return (
      <TooltipHint content={<span className="break-all" data-link-hint>{href}</span>}>
        <a className={cn("font-medium text-primary underline", className)} href={href} rel="noreferrer" target="_blank" {...rest}>
          {children}
        </a>
      </TooltipHint>
    );
  }
  return (
    <FileLink scope={scope} target={target}>
      {children}
    </FileLink>
  );
}

function FileLink({ scope, target, children }: { scope: TranscriptScope; target: PathTarget; children: ReactNode }) {
  const kind = usePathKind(scope, target.path);
  const lookup = usePathLinks((state) => state.lookup);
  useEffect(() => {
    if (kind === undefined) {
      lookup(scope, [target.path]);
    }
  }, [kind, lookup, scope, target.path]);

  if (kind !== "file" && kind !== "directory") {
    return <span data-path-text={target.path}>{children}</span>;
  }

  const reference = kind === "file" && target.selector && isCadFile(target.path) ? target.selector : "";
  const Icon = kind === "directory" ? Folder : isCadFile(target.path) ? Box : FileText;
  const open = () => {
    const explorer = useExplorer.getState();
    if (kind === "directory") {
      explorer.revealPath(target.path, true, scope.root);
      return;
    }
    const tab = explorer.openFile(target.path, scope.root);
    if (tab && reference) {
      explorer.selectCadReference(tab.id, reference);
    }
  };
  return (
    <TooltipHint content={reference ? `Open ${target.path} and select ${reference}` : kind === "directory" ? `Reveal ${target.path}` : `Open ${target.path}`}>
      <button
        className="inline-flex max-w-full items-baseline gap-1 rounded-sm font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        data-path-link={target.path}
        data-path-selector={reference || undefined}
        data-path-kind={kind}
        onClick={open}
        type="button"
      >
        <Icon aria-hidden className="size-3 shrink-0 self-center opacity-70" />
        <span className="min-w-0 break-all">{children}</span>
      </button>
    </TooltipHint>
  );
}
