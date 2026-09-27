import { clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// text-micro and text-tiny are font sizes from the type scale in
// styles/globals.css. tailwind-merge only knows Tailwind's stock sizes, so
// without this it reads them as text colours and drops them whenever a
// text-<colour> class follows in the same cn() call.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["micro", "tiny"] }]
    }
  }
});

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
