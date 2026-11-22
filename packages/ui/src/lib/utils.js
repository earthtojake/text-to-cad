import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// text-tiny, text-ui and text-heading are font sizes from the type scale in
// styles/globals.css. tailwind-merge only knows Tailwind's stock sizes, so
// without this it reads them as text colours: it drops them whenever a
// text-<colour> class follows in the same cn() call, and keeps a primitive's
// own size (a button's text-xs) beside them, which then wins.
// The same for THE scale's sizes (`styles/globals.css`, `tokens.css`'s `--spacing-*` and `--radius-control`): a later
// `size-control` replaces a primitive's `size-icon-button`, as `size-7` would replace `size-6`.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      spacing: ["control", "icon-button", "row", "row-sm", "glyph", "glyph-sm", "pad", "step", "thumb"],
      radius: ["control"]
    },
    classGroups: {
      "font-size": [{ text: ["tiny", "ui", "heading"] }]
    }
  }
});

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
