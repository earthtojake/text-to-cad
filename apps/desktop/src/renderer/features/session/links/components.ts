import type { ReactNode } from "react";
import { defaultRehypePlugins } from "streamdown";

import { PathLink } from "./PathLink";
import { rehypeProjectImages } from "./rehypeProjectImages";
import { TranscriptImage } from "./TranscriptImage";

/**
 * What the transcript's markdown draws its own way — prose and thoughts
 * alike: a link through `PathLink`, an image through `TranscriptImage`. A
 * module constant, because `MessageResponse` is memoised on its children and
 * a fresh object per render would rebuild every block.
 *
 * `<picture>` and `<source>` pass Streamdown's sanitizer, and `srcset` is
 * checked against no protocol list: a `<source srcset="https://…">` beside a
 * project image the transcript does draw is a request on paint, the browser
 * preferring the source to its `<img>`. So a source draws nothing and a
 * picture is only its children.
 */
export const TRANSCRIPT_COMPONENTS = {
  a: PathLink,
  img: TranscriptImage,
  picture: ({ children }: { children?: ReactNode }) => children,
  source: () => null,
};

/**
 * Streamdown's own rehype plugins — raw HTML, the sanitizer, harden — with
 * `rehypeProjectImages` between the sanitizer and harden, so a project image
 * named without a `./` reaches `TranscriptImage` instead of being blocked.
 * `rehypePlugins` *replaces* Streamdown's defaults, so they are spread back in
 * around it. A module constant, for the memoised `MessageResponse`.
 */
const { harden, ...beforeHarden } = defaultRehypePlugins;
export const TRANSCRIPT_REHYPE_PLUGINS = [...Object.values(beforeHarden), rehypeProjectImages, ...(harden ? [harden] : [])];
