import Link from "next/link";

// The documentation and the site's legal pages, then who made it, at the right; wrapping on a phone.
// `wide`: as wide as the documentation's columns.
export function SiteFooter({ wide = false }: { wide?: boolean }) {
  return (
    <footer className="border-t border-border py-6">
      <div className={`mx-auto flex w-full flex-wrap justify-end gap-4 px-4 text-xs text-muted-foreground sm:px-6 ${wide ? "max-w-[1400px]" : "max-w-[1200px]"}`}>
        <Link className="transition hover:text-primary" href="/docs">
          Docs
        </Link>
        <a className="transition hover:text-primary" href="/privacy-policy">
          Privacy Policy
        </a>
        <a className="transition hover:text-primary" href="/terms-of-service">
          Terms of Service
        </a>
        <a
          className="transition hover:text-primary"
          href="https://x.com/earthtojake"
          target="_blank"
          rel="noreferrer"
        >
          Made by @earthtojake
        </a>
      </div>
    </footer>
  );
}
