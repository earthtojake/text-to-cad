# Loading icon

Silver renders of Jake's animated icon from [PR #374](https://github.com/earthtojake/text-to-cad/pull/374),
source commit `ed6a16b25936031adfa0a6d4705d80e1c712eb37`.
The geometry remains owned by the docs icon generator; it is not copied into
the viewer runtime.

`hardcore-loading.webp` is a transparent 192 × 192, 20 fps, 20-second loop.
It preserves the playground's default two-second contraction and twenty-second
orbit, using its Silver material and studio lighting. `hardcore-still.webp`
is the fully expanded reference pose. The viewer displays both at 96 × 96.

The animation is decorative. Existing loading state, status labels and measured
progress still control the overlay. OS reduced motion, the desktop's Reduce
motion setting, and document visibility select the still image. No additional
WebGL context or animation loop runs in the application.

To regenerate, install the desktop dependencies, Chromium for Playwright, and
the WebP CLI tools (`img2webp`, `cwebp`). Then, from the repository root:

```sh
git fetch upstream pull/374/head
node scripts/brand/render-loading-icon.mjs
```

The script reads the pinned Git source, so later changes to the PR do not
silently change the brand. Normal viewer and desktop builds consume these
checked-in images and need neither Git access nor the rendering tools.
