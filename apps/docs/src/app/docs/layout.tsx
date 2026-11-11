import type { ReactNode } from "react";
import { DocsMobileNav } from "@/components/docs/mobile-nav";
import { DocsSearch } from "@/components/docs/search";
import { DocsSidebar } from "@/components/docs/sidebar";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { navigation } from "@/lib/docs/source";

/** The documentation's shell, under the site's header: the sections at the left (a drawer on a phone
 * or a tablet), with the search over them, and the page beside them. */
export default function DocsLayout({ children }: { children: ReactNode }) {
  const sections = navigation();
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <SiteHeader wide />
      <DocsMobileNav sections={sections} />
      <div className="mx-auto flex w-full max-w-[1400px] flex-1 px-4 sm:px-6">
        <aside className="sticky top-14 hidden h-[calc(100svh-3.5rem)] w-60 shrink-0 flex-col gap-4 py-6 pr-4 lg:flex">
          <DocsSearch shortcut />
          <div className="-mr-2 min-h-0 flex-1 overflow-y-auto pr-2">
            <DocsSidebar sections={sections} />
          </div>
        </aside>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
      <SiteFooter wide />
    </div>
  );
}
