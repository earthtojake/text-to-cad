import Link from "next/link";
import type { ReactNode } from "react";

// A plain legal page: prose rendered on the server, so a person or an automated reviewer reads it
// without running the site's scripts. Nothing in the site's navigation links here.
export function LegalPage({
  title,
  updated,
  summary,
  children,
}: {
  title: string;
  updated: string;
  summary: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto min-h-screen max-w-2xl bg-background px-6 py-16 text-foreground">
      <Link href="/" className="text-sm text-muted-foreground">
        ← text-to-cad
      </Link>
      <h1 className="mt-10 text-3xl font-medium tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>
      <p className="mt-6 leading-7">{summary}</p>
      <div className="mt-8 space-y-8">{children}</div>
    </main>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-medium">{title}</h2>
      <p className="mt-2 leading-7 text-muted-foreground">{children}</p>
    </section>
  );
}

export function IssuesLink() {
  return (
    <a
      className="underline underline-offset-4 hover:text-foreground"
      href="https://github.com/earthtojake/text-to-cad/issues"
    >
      github.com/earthtojake/text-to-cad/issues
    </a>
  );
}
