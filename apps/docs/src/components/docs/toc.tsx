"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type TocHeading = { depth: number; id: string; text: string };

/** "On this page": the page's sections, the one being read marked as the page scrolls. */
export function DocsToc({ headings }: { headings: TocHeading[] }) {
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const elements = headings.flatMap(({ id }) => document.getElementById(id) ?? []);
    if (!elements.length) return;
    // The section being read: the last heading above a line a little under the header.
    const mark = () => {
      const passed = elements.filter((element) => element.getBoundingClientRect().top <= 96);
      setActive((passed.at(-1) ?? elements[0]).id);
    };
    mark();
    window.addEventListener("scroll", mark, { passive: true });
    return () => window.removeEventListener("scroll", mark);
  }, [headings]);

  if (headings.length < 2) return null;

  return (
    <nav aria-label="On this page" className="text-sm">
      <p className="mb-2 text-label font-medium tracking-[0.1em] text-muted-foreground uppercase">On this page</p>
      <ul className="space-y-px border-l border-border">
        {headings.map(({ depth, id, text }) => (
          <li key={id}>
            <a
              href={`#${id}`}
              className={cn(
                "-ml-px block border-l py-1 leading-5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                depth > 2 ? "pl-6" : "pl-3",
                active === id
                  ? "border-brand text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
