import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// text-micro, text-tiny and text-ui are font sizes from the type scale in
// styles/globals.css. tailwind-merge only knows Tailwind's stock sizes, so
// without this it reads them as text colours: it drops them whenever a
// text-<colour> class follows in the same cn() call, and keeps a primitive's
// own size (a button's text-xs) beside them, which then wins.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["micro", "tiny", "ui"] }]
    }
  }
});

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
