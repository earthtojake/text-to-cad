import Image from "next/image";
import { Download, ExternalLink } from "lucide-react";
import { formatSize, getDesktopDownloads } from "@/lib/desktop-downloads";

/**
 * The desktop app, shown and downloadable. The app itself is the argument —
 * a looping capture of one session beside the download buttons, and three
 * stills under it — so the section reads before it is read: a chat on the
 * left, a model on the right, a note pinned to a face.
 *
 * Captures come from the real app over a fixture folder
 * (`apps/desktop/tmp/probe/site-assets.mjs`, not committed): 1280×800, light.
 * `public/desktop/` holds them; the video is WebM, which every current
 * browser plays, with the annotation still as its poster.
 */

const STILLS = [
  {
    src: "/desktop/annotate.png",
    alt: "A STEP model open beside the chat, with a numbered annotation pinned to a boss and its note: make this boss 2 mm taller",
    caption: "Point at a face and say what should change. The note goes to the chat box.",
  },
  {
    src: "/desktop/sketch.png",
    alt: "A red pen stroke drawn over the model, with the Draw tools open and an Annotate button below",
    caption: "Sketch over the model when words are not enough; the drawing travels with the note.",
  },
  {
    src: "/desktop/chat.png",
    alt: "The chat box's annotation list: a face note, and a sketch note with its thumbnail",
    caption: "Everything pinned is one list in the chat box, edited in place, sent with the prompt.",
  },
] as const;

export async function DesktopSection() {
  const downloads = await getDesktopDownloads();
  return (
    <section id="desktop" aria-labelledby="desktop-title" className="scroll-mt-20 space-y-4 py-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-start">
        <div className="space-y-4">
          {/* The app's own icon leads, as an app page's does: the tile people will see in their dock. */}
          <div className="flex items-start gap-4">
            <Image
              src="/desktop/icon.png"
              alt=""
              width={72}
              height={72}
              className="size-[72px] shrink-0 rounded-[18px] shadow-lg shadow-black/25"
              priority
            />
            <div className="min-w-0">
              <h2 id="desktop-title" className="text-heading font-medium tracking-normal text-foreground">
                DESKTOP APP
              </h2>
              <p className="mt-1 text-label uppercase tracking-[1.5px] text-muted-foreground">
                text-to-cad for macOS, Windows and Linux
              </p>
            </div>
          </div>
          <div>
            <p className="text-sm leading-6 text-muted-foreground">
              Your folders on the left, the agent in the middle, a CAD viewer on the right. Open a
              STEP, pin a note to a face, sketch a change, and send it. cadgen and every skill ship
              inside, so nothing installs on first launch.
            </p>
          </div>

          {downloads.installers.length > 0 ? (
            <div className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {downloads.installers.map((installer) => (
                <a
                  key={installer.id}
                  className="card-glow flex min-w-0 items-center gap-3 border border-border bg-card px-3.5 py-3 transition hover:bg-secondary/60"
                  href={installer.url}
                  data-desktop-installer={installer.id}
                >
                  <Download className="size-4 shrink-0 text-primary" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-foreground">{installer.platform}</span>
                    <span className="block text-label uppercase tracking-[1.5px] text-muted-foreground">{installer.detail}</span>
                  </span>
                  <span className="shrink-0 text-label text-muted-foreground">{formatSize(installer.size)}</span>
                </a>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-muted-foreground" data-desktop-installers="none">
              Installers for macOS, Windows and Linux are attached to each release once the app is in
              it. Watch the{" "}
              <a
                className="inline-flex items-center gap-1 text-primary transition hover:text-primary/80"
                href={downloads.releaseUrl}
                rel="noreferrer"
                target="_blank"
              >
                releases page
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
              , or build it from the repository with <code className="text-foreground">npm run package:mac</code>.
            </p>
          )}

          <p className="text-sm leading-6 text-muted-foreground">
            {downloads.version ? (
              <>
                <span className="text-foreground">Version {downloads.version}.</span>{" "}
              </>
            ) : null}
            The app checks these same releases for updates and asks before it downloads one. macOS
            builds are not yet signed: control-click the app and choose Open the first time.{" "}
            <a
              className="inline-flex items-center gap-1 text-primary transition hover:text-primary/80"
              href={downloads.releaseUrl}
              rel="noreferrer"
              target="_blank"
            >
              All releases
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          </p>
        </div>

        <figure className="min-w-0">
          <div className="card-glow overflow-hidden border border-border bg-card">
            {/* Muted and looping, so it plays without a press; the poster is the first still, for a browser that will not. */}
            <video
              className="block aspect-[16/10] w-full bg-background"
              autoPlay
              loop
              muted
              playsInline
              poster="/desktop/annotate.png"
              preload="metadata"
              aria-label="A short capture of the desktop app: a part opens from the chat, a face is annotated, a sketch is drawn and annotated, and both notes appear in the chat box"
            >
              <source src="/desktop/tour.webm" type="video/webm" />
            </video>
          </div>
          <figcaption className="mt-2 text-label uppercase tracking-[1.5px] text-muted-foreground">
            One session: open, annotate, sketch, send
          </figcaption>
        </figure>
      </div>

      <ul className="grid gap-3 sm:grid-cols-3" aria-label="The desktop app in stills">
        {STILLS.map((still) => (
          <li key={still.src} className="min-w-0">
            <a className="card-glow block overflow-hidden border border-border bg-card" href={still.src} target="_blank" rel="noreferrer">
              <Image src={still.src} alt={still.alt} width={1280} height={800} className="block h-auto w-full" sizes="(min-width: 640px) 33vw, 100vw" />
            </a>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{still.caption}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
