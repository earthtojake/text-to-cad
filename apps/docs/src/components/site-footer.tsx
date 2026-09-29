export function SiteFooter() {
  return (
    <footer className="border-t border-border py-6">
      <div className="mx-auto flex w-full max-w-[1200px] justify-end px-4 text-xs text-muted-foreground sm:px-6">
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
