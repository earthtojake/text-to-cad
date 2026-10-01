import { ImageOff } from "lucide-react";
import { useContext, useEffect, useState, type ImgHTMLAttributes } from "react";

import { cn } from "@renderer/lib/utils";

import { pathTarget, TranscriptScopeContext, type TranscriptScope } from "./PathLink";

/**
 * The transcript's `img`. An image in the agent's words is drawn only when
 * nothing leaves the machine to draw it: a file in the project read through
 * the explorer the way a link to it opens (`pathTarget`, then main's own
 * resolution against the scope). Anything else — an `https:` image, a raw
 * `<img>` — is a request on paint, and whatever the agent put in its query
 * string would go with it, so it is the address as words instead. A `data:`
 * image never reaches here with its `src`: Streamdown's sanitizer admits only
 * `http:`, `https:` and relative sources, and drops the rest before any
 * component sees them.
 *
 * The page's policy admits `https:` images (a CAD view's textures), and
 * Streamdown's defaults admit any image prefix, so this is the one place the
 * transcript refuses them (`<source srcset>` is refused beside it, in
 * `TRANSCRIPT_COMPONENTS`).
 */
export function TranscriptImage({
  src,
  alt,
  className,
  node: _node,
}: ImgHTMLAttributes<HTMLImageElement> & { node?: unknown }) {
  const scope = useContext(TranscriptScopeContext);
  const source = typeof src === "string" ? src : "";
  const target = pathTarget(source);
  if (target && scope) {
    return <ProjectImage alt={alt} className={className} path={target.path} scope={scope} />;
  }
  return <ImageAddress address={source} />;
}

/** A project file's bytes, read once per path as a `data:` URL; the address until they land. */
function ProjectImage({ scope, path, alt, className }: { scope: TranscriptScope; path: string; alt?: string; className?: string }) {
  const [read, setRead] = useState<{ path: string; dataUrl: string } | null>(null);
  useEffect(() => {
    let live = true;
    window.textToCad.explorer
      .readBinary({ projectId: scope.projectId, ...(scope.root ? { root: scope.root } : {}), path })
      .then((binary) => {
        if (live && binary.mime.startsWith("image/") && binary.dataUrl.startsWith("data:image/")) {
          setRead({ path, dataUrl: binary.dataUrl });
        }
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [scope.projectId, scope.root, path]);
  const dataUrl = read?.path === path ? read.dataUrl : null;
  if (!dataUrl) {
    return <ImageAddress address={path} />;
  }
  return <img alt={alt ?? ""} className={cn("my-1 max-h-80 w-fit rounded-lg border", className)} data-transcript-image={path} src={dataUrl} />;
}

function ImageAddress({ address }: { address: string }) {
  return (
    <span
      className="not-prose inline-flex max-w-full items-baseline gap-1 rounded-md border px-1.5 text-[12px] text-muted-foreground"
      data-image-address
    >
      <ImageOff aria-hidden className="size-3 shrink-0 self-center" />
      <span className="min-w-0 break-all">{address || "Image"}</span>
    </span>
  );
}
