# Loading icon

Blue renders of Jake's animated icon from [PR #374](https://github.com/earthtojake/text-to-cad/pull/374),
source commit `ed6a16b25936031adfa0a6d4705d80e1c712eb37`.
The geometry remains owned by the docs icon generator; it is not copied into
the viewer runtime.

`loading.avif` is a transparent 192 × 192, 20 fps, 20-second loop (animated AVIF,
quality 70, 4:4:4: about 510 KB).
It preserves the playground's default two-second contraction and twenty-second
orbit, using the brand blue (`#62b7ec`) and studio lighting. `loading-still.webp`
is the fully expanded reference pose. The viewer displays both at 96 × 96.

The animation is decorative. Existing loading state, status labels and measured
progress still control the overlay. The still image shows when the system
prefers reduced motion, when the document is hidden, or when the icon's
`reducedMotion` prop is set — the viewer passes the host's
`environment.reducedMotion` (the desktop's Reduce motion setting). No additional
WebGL context or animation loop runs in the application.

To regenerate, run `npm ci` at the repository root, then install Chromium for Playwright and
the repo's Python (`.venv`; its Pillow encodes AVIF and WebP). Then, from the repository root:

```sh
git fetch upstream pull/374/head
node scripts/brand/render-loading-icon.mjs
```

The script reads the pinned Git source, so later changes to the PR do not
silently change the brand. Normal viewer and desktop builds consume these
checked-in images and need neither Git access nor the rendering tools.
