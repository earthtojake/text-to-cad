"use client";

import { Menu, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import { DocsSearch } from "@/components/docs/search";
import { DocsSidebar, type DocsNavigation } from "@/components/docs/sidebar";

/** The documentation's bar on a phone or a tablet, under the header: the sections, in a drawer, and
 * the search. A wider screen has the sidebar instead. */
export function DocsMobileNav({ sections }: { sections: DocsNavigation }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sticky top-14 z-30 flex items-center gap-2 border-b border-border bg-background px-4 py-2 sm:px-6 lg:hidden">
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Trigger asChild>
          <button
            type="button"
            className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border border-border bg-background px-2.5 text-sm font-medium text-foreground outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring dark:bg-input/30"
          >
            <Menu className="size-4" aria-hidden="true" />
            Menu
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
          <Dialog.Content
            aria-describedby={undefined}
            className="fixed inset-y-0 left-0 z-50 flex w-[min(20rem,calc(100vw-3rem))] flex-col border-r border-border bg-background outline-none"
          >
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
              <Dialog.Title className="text-sm font-semibold">Documentation</Dialog.Title>
              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Close the menu"
                  className="inline-flex size-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              <DocsSidebar sections={sections} onNavigate={() => setOpen(false)} />
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <DocsSearch className="min-w-0 flex-1" />
    </div>
  );
}
